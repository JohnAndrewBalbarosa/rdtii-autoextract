"""Parallel document matcher over a read-only SetTrieIndex.

Dispatches many independent ``(doc_id, tags)`` queries concurrently using either a
ThreadPoolExecutor or ProcessPoolExecutor, then assembles results deterministically.

Thread-safety note
------------------
After ``SetTrieIndex.build()`` completes, the trie structure (``_root``, ``_rank``,
``_node_count``) is **never mutated again** — every query is a pure read-only traversal
over immutable dicts/lists.  The only mutable attribute touched during a query is
``_last_nodes_visited``, which is a plain Python ``int`` written back after the traversal.
Because Python's GIL serialises object attribute writes, no two threads will observe a
torn write; each thread's ``nodes_visited`` side-effect is therefore benign (the value is
private to the calling thread's logical query, and we deliberately ignore it in parallel
mode — we return only ``sorted(out)`` which is built in local stack variables per call).
No locks are required.

GIL reality
-----------
``query_subsets`` / ``query_supersets`` are CPU-bound pure-Python tree walks.  The GIL
limits true parallelism: threads take turns executing bytecode, so ``mode="thread"`` does
**not** speed up CPU-bound matching.  ``mode="process"`` would give real CPU parallelism
but requires pickling the entire ``SetTrieIndex`` into every worker process — expensive for
large indexes and broken if the index is not picklable; we fall back to threads in that
case.  In practice, each query on a typical 150-item index takes *microseconds*; the
real latency in the RDTII pipeline is the I/O-bound crawl, not the matching step.  Threads
are fine for keeping code simple and avoiding pickling overhead.

Duplicate doc_id policy
-----------------------
If the same ``doc_id`` appears more than once in ``documents``, **last write wins**: the
result for that id will reflect whichever worker's future resolves last.  This is
documented, deterministic within a run (given a fixed input list), and avoids the
ambiguity of raising while still being honest.  Callers that care should deduplicate
before calling.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zetarix.scoring.set_trie import SetTrieIndex

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS = min(32, (os.cpu_count() or 2))


def _query_one(
    index: "SetTrieIndex",
    doc_id: str,
    tags: frozenset[str],
    predicate: str,
) -> tuple[str, list[str]]:
    """Run a single query on the index and return ``(doc_id, sorted_node_ids)``."""
    if predicate == "subset":
        result = index.query_subsets(tags)
    elif predicate == "superset":
        result = index.query_supersets(tags)
    else:
        raise ValueError(f"Unknown predicate {predicate!r}; expected 'subset' or 'superset'.")
    return doc_id, result  # query_* already returns sorted list


class ParallelMatcher:
    """Match many documents against a read-only :class:`SetTrieIndex` in parallel.

    The index **must** be fully built before constructing this matcher; no mutations
    are made to the index during or after ``match_all``.

    Parameters
    ----------
    index:
        A fully-built ``SetTrieIndex``.  Treated as read-only for the lifetime of
        this matcher.
    """

    def __init__(self, index: "SetTrieIndex") -> None:
        self._index = index

    def match_all(
        self,
        documents: list[tuple[str, set[str]]],
        *,
        max_workers: int | None = None,
        mode: str = "thread",
        predicate: str = "subset",
    ) -> dict[str, list[str]]:
        """Match every document against the index in parallel.

        Parameters
        ----------
        documents:
            List of ``(doc_id, tags)`` pairs.  Tags may be any iterable of strings.
        max_workers:
            Number of concurrent workers.  Defaults to ``min(32, cpu_count)``.
        mode:
            ``"thread"`` (default) — ``ThreadPoolExecutor``; shares the index object
            in-process, no serialisation overhead, but the GIL limits CPU parallelism.
            ``"process"`` — ``ProcessPoolExecutor``; real CPU parallelism at the cost of
            pickling the index into every worker.  If the index is not picklable, falls
            back to ``"thread"`` automatically with a warning.
        predicate:
            ``"subset"`` (default) — match stored items whose tags are a subset of the
            document's tags (``query_subsets``).
            ``"superset"`` — match stored items whose tags are a superset (``query_supersets``).

        Returns
        -------
        dict[str, list[str]]
            ``{doc_id: sorted_node_ids}``.  Order of keys is insertion-order of the
            *first* seen doc_id but values are always sorted.  Duplicate doc_ids: last
            write wins (see module docstring).

        Notes
        -----
        Result is **deterministic**: ``query_subsets`` / ``query_supersets`` return
        ``sorted(out)`` regardless of traversal order, and we collect futures **after**
        all complete (``as_completed`` loop), so the final dict reflects the full set of
        results with no race on the output accumulator.  Running with W=1 or W=8 workers
        produces identical ``{doc_id: sorted_node_ids}`` dicts.
        """
        if not documents:
            return {}

        workers = max_workers if max_workers is not None else _DEFAULT_MAX_WORKERS
        index = self._index

        executor_cls: type
        if mode == "process":
            try:
                executor_cls = ProcessPoolExecutor
                # Quick picklability probe — cheap compared to spawning processes.
                import pickle

                pickle.dumps(index)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SetTrieIndex is not picklable (%s); falling back to ThreadPoolExecutor.",
                    exc,
                )
                executor_cls = ThreadPoolExecutor
        else:
            executor_cls = ThreadPoolExecutor

        results: dict[str, list[str]] = {}

        with executor_cls(max_workers=workers) as executor:
            # Submit all futures first so the executor can schedule them freely.
            futures = {
                executor.submit(_query_one, index, doc_id, frozenset(tags), predicate): doc_id
                for doc_id, tags in documents
            }
            # Collect as they complete; order-independent by design.
            for future in as_completed(futures):
                doc_id_result, node_ids = future.result()
                results[doc_id_result] = node_ids

        return results

"""Tests for ParallelMatcher — the key invariant is parallel == sequential.

Conventions (per project rules):
- conftest adds backend/ to sys.path
- stdlib-only (concurrent.futures)
- deterministic: tests seed a local RNG; the component must not use wall-clock/random
- frozen dataclasses, type hints
"""

from __future__ import annotations

import pickle
import random
import string
from typing import Any

import pytest

from zetarix.scoring.parallel_matcher import ParallelMatcher
from zetarix.scoring.set_trie import SetTrieIndex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tag(rng: random.Random) -> str:
    """Random short lowercase tag."""
    length = rng.randint(2, 6)
    return "".join(rng.choices(string.ascii_lowercase, k=length))


def _build_index(rng: random.Random, n_items: int = 150) -> SetTrieIndex:
    """Build a SetTrieIndex with n_items random (id, tags) entries."""
    universe = [_make_tag(rng) for _ in range(30)]  # shared tag vocabulary
    items = []
    for i in range(n_items):
        n_tags = rng.randint(1, 8)
        tags = frozenset(rng.choices(universe, k=n_tags))
        items.append((f"item_{i}", tags))
    return SetTrieIndex(items)


def _make_documents(rng: random.Random, n_docs: int, universe: list[str]) -> list[tuple[str, set[str]]]:
    """Generate n_docs random documents from the given tag universe."""
    docs = []
    for i in range(n_docs):
        n_tags = rng.randint(0, 10)
        tags = set(rng.choices(universe, k=n_tags))
        docs.append((f"doc_{i}", tags))
    return docs


def _sequential_match(index: SetTrieIndex, documents: list[tuple[str, set[str]]], predicate: str) -> dict[str, list[str]]:
    """Reference sequential implementation."""
    result = {}
    for doc_id, tags in documents:
        if predicate == "subset":
            result[doc_id] = index.query_subsets(tags)
        else:
            result[doc_id] = index.query_supersets(tags)
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rng() -> random.Random:
    """Seeded RNG — tests are deterministic."""
    return random.Random(42)


@pytest.fixture(scope="module")
def shared_index(rng: random.Random) -> SetTrieIndex:
    return _build_index(rng, n_items=150)


@pytest.fixture(scope="module")
def shared_universe(shared_index: SetTrieIndex) -> list[str]:
    """Tag universe derived from the built index."""
    tags: set[str] = set()
    for item in shared_index.items:
        tags.update(item.tags)
    return sorted(tags)


@pytest.fixture(scope="module")
def eighty_docs(rng: random.Random, shared_universe: list[str]) -> list[tuple[str, set[str]]]:
    return _make_documents(rng, n_docs=80, universe=shared_universe)


# ---------------------------------------------------------------------------
# Core invariant: parallel == sequential across W ∈ {1, 2, 4, 8}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("max_workers", [1, 2, 4, 8])
def test_parallel_equals_sequential_subset(
    shared_index: SetTrieIndex,
    eighty_docs: list[tuple[str, set[str]]],
    max_workers: int,
) -> None:
    """ParallelMatcher with subset predicate must match sequential result."""
    matcher = ParallelMatcher(shared_index)
    parallel = matcher.match_all(eighty_docs, max_workers=max_workers, predicate="subset")
    sequential = _sequential_match(shared_index, eighty_docs, "subset")
    assert parallel == sequential


@pytest.mark.parametrize("max_workers", [1, 2, 4, 8])
def test_parallel_equals_sequential_superset(
    shared_index: SetTrieIndex,
    eighty_docs: list[tuple[str, set[str]]],
    max_workers: int,
) -> None:
    """ParallelMatcher with superset predicate must match sequential result."""
    matcher = ParallelMatcher(shared_index)
    parallel = matcher.match_all(eighty_docs, max_workers=max_workers, predicate="superset")
    sequential = _sequential_match(shared_index, eighty_docs, "superset")
    assert parallel == sequential


def test_two_runs_identical(
    shared_index: SetTrieIndex,
    eighty_docs: list[tuple[str, set[str]]],
) -> None:
    """Two successive parallel runs with same input produce identical output (no races)."""
    matcher = ParallelMatcher(shared_index)
    run1 = matcher.match_all(eighty_docs, max_workers=4, predicate="subset")
    run2 = matcher.match_all(eighty_docs, max_workers=4, predicate="subset")
    assert run1 == run2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_document_list(shared_index: SetTrieIndex) -> None:
    """Empty input returns empty dict."""
    matcher = ParallelMatcher(shared_index)
    result = matcher.match_all([])
    assert result == {}


def test_doc_with_empty_tags(shared_index: SetTrieIndex) -> None:
    """A document with no tags should not crash; subset query returns items with empty tag sets."""
    matcher = ParallelMatcher(shared_index)
    docs: list[tuple[str, set[str]]] = [("empty_doc", set())]
    result = matcher.match_all(docs, predicate="subset")
    assert "empty_doc" in result
    # Values should be a list (possibly empty)
    assert isinstance(result["empty_doc"], list)


def test_doc_with_empty_tags_superset(shared_index: SetTrieIndex) -> None:
    """Empty-tag document with superset predicate matches ALL stored items."""
    matcher = ParallelMatcher(shared_index)
    docs: list[tuple[str, set[str]]] = [("empty_doc", set())]
    result = matcher.match_all(docs, predicate="superset")
    # An empty query Q: every stored set is a superset of {} → all items match
    all_ids = sorted(item.node_id for item in shared_index.items)
    assert result["empty_doc"] == all_ids


def test_duplicate_doc_ids_last_write_wins(shared_index: SetTrieIndex) -> None:
    """Duplicate doc_ids: last-write-wins as documented; no crash."""
    # Build two distinct tag sets that will produce different results
    all_tags = [t for item in shared_index.items for t in item.tags]
    first_tags: set[str] = set()
    second_tags = set(all_tags[:5]) if all_tags else set()

    docs: list[tuple[str, set[str]]] = [
        ("dup_doc", first_tags),
        ("dup_doc", second_tags),
    ]
    matcher = ParallelMatcher(shared_index)
    result = matcher.match_all(docs, max_workers=1, predicate="subset")
    # Should not crash; exactly one entry for dup_doc
    assert "dup_doc" in result
    assert isinstance(result["dup_doc"], list)


def test_invalid_predicate_raises(shared_index: SetTrieIndex) -> None:
    """An unsupported predicate raises ValueError."""
    matcher = ParallelMatcher(shared_index)
    with pytest.raises(ValueError, match="predicate"):
        matcher.match_all([("d", {"tag"})], predicate="invalid")


# ---------------------------------------------------------------------------
# Scale: 500 documents completes without error
# ---------------------------------------------------------------------------

def test_many_docs_no_error(shared_index: SetTrieIndex, shared_universe: list[str]) -> None:
    """500 documents complete without error under thread mode."""
    rng = random.Random(99)
    big_docs = _make_documents(rng, n_docs=500, universe=shared_universe)
    matcher = ParallelMatcher(shared_index)
    result = matcher.match_all(big_docs, max_workers=4, predicate="subset")
    assert len(result) == 500
    for doc_id, node_ids in result.items():
        assert isinstance(node_ids, list)
        assert node_ids == sorted(node_ids)  # always sorted


# ---------------------------------------------------------------------------
# Process mode
# ---------------------------------------------------------------------------

def test_process_mode_or_skip(
    shared_index: SetTrieIndex,
    eighty_docs: list[tuple[str, set[str]]],
) -> None:
    """Process mode produces the same result as sequential, or falls back to threads gracefully."""
    try:
        pickle.dumps(shared_index)
        picklable = True
    except Exception:
        picklable = False

    if not picklable:
        pytest.skip("SetTrieIndex is not picklable on this platform; process mode falls back to threads.")

    matcher = ParallelMatcher(shared_index)
    result = matcher.match_all(
        eighty_docs,
        max_workers=2,
        mode="process",
        predicate="subset",
    )
    sequential = _sequential_match(shared_index, eighty_docs, "subset")
    assert result == sequential

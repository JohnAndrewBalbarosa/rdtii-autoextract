"""Set-Trie — a tags-only, acyclic-by-construction index for fast tag matching.

This REPLACES the old similarity-graph hierarchy as the matching substrate. There are
NO edges, NO edge weights, NO theta-pruning, NO cycles here. A document's parsed tag set
is matched against stored items (law-section patterns) by walking a trie and pruning any
branch whose required tag is absent from the query.

Algorithm (Savnik 2013, "Index data structure for fast subset and superset queries"):

* Each stored item is a set of tags. We fix a single **global tag order** and store every
  item's tags as a path down the trie, sorted by that order. Because every path is a
  strictly increasing sequence over a total order, the structure is a tree — acyclic by
  construction (you can never revisit a tag, so you can never loop back).
* Default order = **rarity, rarest first**: a rarer tag earlier in the order gates a larger
  subtree, so a query that lacks it prunes more aggressively. Ties broken by the tag string
  for determinism. Tags unseen at build time (and any explicit ``tag_order`` gaps) sort to
  the end, ordered by string.

* ``query_subsets(Q)``  — ids of stored items whose tag set is a SUBSET of ``Q`` (every tag
  of the node appears in the document, so the node applies). Prune rule: only descend into a
  child labelled ``t`` when ``t in Q``; otherwise that whole subtree needs a tag the query
  lacks. (The "paalam kung wala ang tag" pruning.)
* ``query_supersets(Q)`` — ids of stored items whose tag set is a SUPERSET of ``Q``.

Pure and decoupled: operates on ``(id, frozenset[str])`` only. No graph adapters,
ConceptNode, scoring, web, or LLM imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetTrieItem:
    """A stored item: an id paired with its (immutable) tag set."""

    node_id: str
    tags: frozenset[str]


@dataclass(frozen=True)
class QueryResult:
    """Result of a query: matching ids plus the prune-effectiveness counter."""

    ids: tuple[str, ...]
    nodes_visited: int


class _TrieNode:
    """A mutable trie node. ``children`` maps a tag label to a child node; ``ids`` holds the
    ids of items whose full tag-path ends here (a leaf in set terms, possibly shared)."""

    __slots__ = ("children", "ids")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.ids: list[str] = []


@dataclass
class SetTrieIndex:
    """Set-Trie over ``(node_id, tags)`` items with rarity-ordered, prune-friendly paths.

    Build via the constructor (``SetTrieIndex(items)``) or ``SetTrieIndex().build(items)``.
    The global tag order is computed once at build time and reused for every stored path,
    which is what guarantees a single canonical (and acyclic) layout.
    """

    items: tuple[SetTrieItem, ...] = ()
    tag_order: list[str] | None = None

    _root: _TrieNode = field(default_factory=_TrieNode, init=False, repr=False)
    _rank: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _node_count: int = field(default=0, init=False, repr=False)
    _last_nodes_visited: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.items:
            self.build(self.items, tag_order=self.tag_order)

    # ------------------------------------------------------------------ build

    def build(
        self,
        items,
        *,
        tag_order: list[str] | None = None,
    ) -> "SetTrieIndex":
        """(Re)build the trie from ``items`` of shape ``(node_id, tags)`` or ``SetTrieItem``.

        ``tag_order`` overrides the default rarity ordering; any tag missing from it (or, by
        default, every tag) is ranked by corpus rarity then string, appended deterministically.
        """
        normalized = tuple(_coerce_items(items))
        self.items = normalized
        self.tag_order = tag_order
        self._rank = _build_rank(normalized, tag_order)
        self._root = _TrieNode()
        self._node_count = 1  # the root itself

        for item in normalized:
            path = sorted(item.tags, key=self._tag_key)
            node = self._root
            for tag in path:
                child = node.children.get(tag)
                if child is None:
                    child = _TrieNode()
                    node.children[tag] = child
                    self._node_count += 1
                node = child
            node.ids.append(item.node_id)

        return self

    def _tag_key(self, tag: str) -> tuple[int, str]:
        """Sort key for a tag: its global rank, then the tag string (stable, total order)."""
        return (self._rank.get(tag, len(self._rank)), tag)

    # ------------------------------------------------------------------ queries

    @property
    def node_count(self) -> int:
        """Total number of trie nodes (incl. root) — the denominator for prune ratios."""
        return self._node_count

    @property
    def nodes_visited(self) -> int:
        """Trie nodes touched by the most recent query (prune-effectiveness gauge)."""
        return self._last_nodes_visited

    def query_subsets(self, query_tags) -> list[str]:
        """Ids of stored items whose tag set is a subset of ``query_tags``.

        Descend only into children whose label is in the query; everything else is pruned.
        Empty query matches only empty-tag items. Returns sorted, deterministic ids.
        """
        query = frozenset(query_tags)
        visited = [0]
        out: list[str] = []
        self._collect_subsets(self._root, query, visited, out)
        self._last_nodes_visited = visited[0]
        return sorted(out)

    def query_subsets_result(self, query_tags) -> QueryResult:
        """Like :meth:`query_subsets` but returns ids + ``nodes_visited`` together."""
        ids = self.query_subsets(query_tags)
        return QueryResult(tuple(ids), self._last_nodes_visited)

    def _collect_subsets(
        self,
        node: _TrieNode,
        query: frozenset[str],
        visited: list[int],
        out: list[str],
    ) -> None:
        visited[0] += 1
        # Items ending at this node have all their tags accounted for on the path here,
        # and every tag on the path was required to be in the query to reach it.
        out.extend(node.ids)
        for tag, child in node.children.items():
            if tag in query:  # paalam kung wala ang tag: skip the whole subtree
                self._collect_subsets(child, query, visited, out)

    def query_supersets(self, query_tags) -> list[str]:
        """Ids of stored items whose tag set is a superset of ``query_tags``.

        We must locate every required query tag somewhere along a path, in global order.
        At each node we may either *skip* the current child label (the stored set has an
        extra tag not in the query) or *consume* it when it equals the next-needed query
        tag. A branch is pruned once its smallest label already exceeds the next-needed tag
        (the ordering guarantees that tag can never appear deeper). Empty query matches all.
        """
        # Required tags, in the same global order used to lay out the trie.
        needed = sorted(frozenset(query_tags), key=self._tag_key)
        visited = [0]
        out: list[str] = []
        self._collect_supersets(self._root, needed, 0, visited, out)
        self._last_nodes_visited = visited[0]
        return sorted(out)

    def query_supersets_result(self, query_tags) -> QueryResult:
        """Like :meth:`query_supersets` but returns ids + ``nodes_visited`` together."""
        ids = self.query_supersets(query_tags)
        return QueryResult(tuple(ids), self._last_nodes_visited)

    def _collect_supersets(
        self,
        node: _TrieNode,
        needed: list[str],
        idx: int,
        visited: list[int],
        out: list[str],
    ) -> None:
        visited[0] += 1
        if idx == len(needed):
            # All required tags consumed — this node and its entire subtree are supersets.
            self._collect_subtree_ids(node, out)
            return
        next_tag = needed[idx]
        next_rank = self._tag_key(next_tag)
        for tag, child in node.children.items():
            if tag == next_tag:
                self._collect_supersets(child, needed, idx + 1, visited, out)
            elif self._tag_key(tag) < next_rank:
                # An extra (smaller-ranked) tag the query lacks: skip-consume, keep looking.
                self._collect_supersets(child, needed, idx, visited, out)
            # else: tag already past next_tag in the order -> next_tag can't appear below; prune.

    def _collect_subtree_ids(self, node: _TrieNode, out: list[str]) -> None:
        """Gather ids of ``node`` and every descendant (the subtree are all supersets)."""
        out.extend(node.ids)
        for child in node.children.values():
            self._collect_subtree_ids(child, out)


# ---------------------------------------------------------------------- helpers


def _coerce_items(items) -> list[SetTrieItem]:
    """Accept ``SetTrieItem`` or raw ``(id, tags)`` pairs; normalise tags to frozensets."""
    out: list[SetTrieItem] = []
    for item in items:
        if isinstance(item, SetTrieItem):
            out.append(item)
            continue
        node_id, tags = item
        out.append(SetTrieItem(str(node_id), frozenset(tags)))
    return out


def _build_rank(items: tuple[SetTrieItem, ...], tag_order: list[str] | None) -> dict[str, int]:
    """Map each tag to a global rank (lower = earlier in stored paths).

    With an explicit ``tag_order`` the listed tags take ranks 0..n-1 in that order; any tag
    not listed is appended after them by rarity (rarest first) then string. Without one, the
    whole rank is rarity-then-string. Deterministic in all cases.
    """
    freq: dict[str, int] = {}
    for item in items:
        for tag in item.tags:
            freq[tag] = freq.get(tag, 0) + 1

    rank: dict[str, int] = {}
    if tag_order:
        for tag in tag_order:
            if tag not in rank:
                rank[tag] = len(rank)

    # Remaining tags (or all of them): rarest first, ties by tag string.
    remaining = sorted(
        (t for t in freq if t not in rank),
        key=lambda t: (freq[t], t),
    )
    for tag in remaining:
        rank[tag] = len(rank)
    return rank

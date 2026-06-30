"""Correctness proof for the Set-Trie index.

The keystone test is *brute-force equivalence*: on randomly generated corpora and queries,
``query_subsets`` / ``query_supersets`` must agree byte-for-byte with the naive O(n) scan.
We also prove pruning actually prunes, determinism, and the documented edge cases.
"""

from __future__ import annotations

import random

from zetarix.scoring.set_trie import SetTrieIndex, SetTrieItem

# A small tag universe makes random subset/superset relations frequent enough to exercise
# both the matching and the pruning paths.
TAG_UNIVERSE = tuple(f"t{i:02d}" for i in range(12))
SEEDS = (1, 7, 42, 1234, 99991)


def _random_corpus(rng: random.Random, n_items: int) -> list[SetTrieItem]:
    items: list[SetTrieItem] = []
    for i in range(n_items):
        k = rng.randint(0, 5)
        tags = frozenset(rng.sample(TAG_UNIVERSE, k))
        items.append(SetTrieItem(f"id{i:04d}", tags))
    return items


def _random_query(rng: random.Random) -> set[str]:
    k = rng.randint(0, len(TAG_UNIVERSE))
    return set(rng.sample(TAG_UNIVERSE, k))


def _brute_subsets(items: list[SetTrieItem], query: set[str]) -> set[str]:
    q = frozenset(query)
    return {it.node_id for it in items if it.tags <= q}


def _brute_supersets(items: list[SetTrieItem], query: set[str]) -> set[str]:
    q = frozenset(query)
    return {it.node_id for it in items if it.tags >= q}


# ---------------------------------------------------------------- brute force


def test_subset_query_matches_brute_force_across_seeds() -> None:
    for seed in SEEDS:
        rng = random.Random(seed)
        items = _random_corpus(rng, 200)
        index = SetTrieIndex(tuple(items))
        for _ in range(100):
            query = _random_query(rng)
            got = index.query_subsets(query)
            assert set(got) == _brute_subsets(items, query), f"seed={seed} q={query}"
            assert got == sorted(got)  # returned sorted & deterministic


def test_superset_query_matches_brute_force_across_seeds() -> None:
    for seed in SEEDS:
        rng = random.Random(seed)
        items = _random_corpus(rng, 200)
        index = SetTrieIndex(tuple(items))
        for _ in range(100):
            query = _random_query(rng)
            got = index.query_supersets(query)
            assert set(got) == _brute_supersets(items, query), f"seed={seed} q={query}"
            assert got == sorted(got)


def test_explicit_tag_order_still_matches_brute_force() -> None:
    rng = random.Random(2026)
    items = _random_corpus(rng, 150)
    # An arbitrary partial order; missing tags must be appended deterministically.
    order = list(TAG_UNIVERSE[6:]) + list(TAG_UNIVERSE[:3])
    index = SetTrieIndex().build(items, tag_order=order)
    for _ in range(80):
        query = _random_query(rng)
        assert set(index.query_subsets(query)) == _brute_subsets(items, query)
        assert set(index.query_supersets(query)) == _brute_supersets(items, query)


# ------------------------------------------------------------------- pruning


def test_subset_pruning_skips_rare_gated_subtree() -> None:
    # A rare tag "rare" gates a large subtree (every item in it shares "rare" + "sub"),
    # while the rest of the corpus shares "common". Forcing "rare" to the front of the
    # order makes the whole gated subtree hang off a single child of the root.
    items: list[SetTrieItem] = []
    for i in range(50):
        items.append(SetTrieItem(f"rare{i}", frozenset({"rare", "sub", f"x{i}"})))
    for i in range(50):
        items.append(SetTrieItem(f"common{i}", frozenset({"common", f"y{i}"})))

    order = ["rare", "common", "sub"] + [f"x{i}" for i in range(50)] + [f"y{i}" for i in range(50)]
    index = SetTrieIndex().build(items, tag_order=order)
    full_node_count = index.node_count

    # A query lacking "rare" must never descend into the rare-gated subtree.
    query_without_rare = {"common"} | {f"y{i}" for i in range(50)}
    index.query_subsets(query_without_rare)
    visited = index.nodes_visited

    assert visited < full_node_count  # genuine pruning happened
    # The 50-item "rare" subtree (>=100 trie nodes) is skipped wholesale, so we visit far
    # fewer nodes than a full per-item scan would.
    assert visited < len(items)


def test_subset_pruning_correctness_under_pruning() -> None:
    items = [SetTrieItem("a", frozenset({"rare", "z"})), SetTrieItem("b", frozenset({"common"}))]
    index = SetTrieIndex(tuple(items))
    # Query has common but not rare -> only b matches, and the rare branch is pruned.
    assert index.query_subsets({"common", "z"}) == ["b"]


# --------------------------------------------------------------- determinism


def test_determinism_identical_results_and_layout() -> None:
    rng = random.Random(555)
    items = _random_corpus(rng, 120)

    index_a = SetTrieIndex(tuple(items))
    index_b = SetTrieIndex(tuple(items))

    # Identical global ordering.
    assert index_a._rank == index_b._rank  # noqa: SLF001 (white-box determinism check)
    assert index_a.node_count == index_b.node_count

    rng_q = random.Random(556)
    for _ in range(60):
        query = _random_query(rng_q)
        assert index_a.query_subsets(query) == index_b.query_subsets(query)
        assert index_a.query_supersets(query) == index_b.query_supersets(query)


def test_rarity_ordering_places_rarest_first() -> None:
    items = [
        SetTrieItem("a", frozenset({"common", "rare"})),
        SetTrieItem("b", frozenset({"common"})),
        SetTrieItem("c", frozenset({"common"})),
    ]
    index = SetTrieIndex(tuple(items))
    # "rare" appears once, "common" three times -> rare ranks earlier (smaller rank).
    assert index._rank["rare"] < index._rank["common"]  # noqa: SLF001


# --------------------------------------------------------------- edge cases


def test_empty_query_matches_only_empty_tag_items_for_subsets() -> None:
    items = [
        SetTrieItem("empty", frozenset()),
        SetTrieItem("nonempty", frozenset({"a"})),
    ]
    index = SetTrieIndex(tuple(items))
    assert index.query_subsets(set()) == ["empty"]


def test_empty_tag_item_is_subset_of_any_query() -> None:
    items = [SetTrieItem("empty", frozenset()), SetTrieItem("x", frozenset({"a", "b"}))]
    index = SetTrieIndex(tuple(items))
    assert "empty" in index.query_subsets({"a", "b", "c"})
    assert "empty" in index.query_subsets(set())


def test_empty_query_is_subset_of_every_stored_set_for_supersets() -> None:
    items = [
        SetTrieItem("p", frozenset({"a"})),
        SetTrieItem("q", frozenset({"a", "b"})),
        SetTrieItem("empty", frozenset()),
    ]
    index = SetTrieIndex(tuple(items))
    # Empty query is a subset of everything -> every stored set is a superset of it.
    assert index.query_supersets(set()) == ["empty", "p", "q"]


def test_duplicate_tag_sets_share_a_leaf_and_both_return() -> None:
    items = [
        SetTrieItem("dup1", frozenset({"a", "b"})),
        SetTrieItem("dup2", frozenset({"a", "b"})),
        SetTrieItem("other", frozenset({"a"})),
    ]
    index = SetTrieIndex(tuple(items))
    assert index.query_subsets({"a", "b"}) == ["dup1", "dup2", "other"]
    assert index.query_supersets({"a", "b"}) == ["dup1", "dup2"]


def test_tags_outside_order_map_assigned_to_end_deterministically() -> None:
    items = [
        SetTrieItem("known", frozenset({"a"})),
        SetTrieItem("unknown", frozenset({"a", "zeta"})),
    ]
    # tag_order omits "zeta"; it must be appended at the end without breaking correctness.
    index = SetTrieIndex().build(items, tag_order=["a"])
    assert index._rank["a"] < index._rank["zeta"]  # noqa: SLF001
    assert set(index.query_subsets({"a", "zeta"})) == {"known", "unknown"}
    assert index.query_subsets({"a"}) == ["known"]


def test_raw_tuple_items_are_accepted() -> None:
    # build() must accept raw (id, tags) pairs, not just SetTrieItem.
    index = SetTrieIndex().build([("x", {"a"}), ("y", {"a", "b"})])
    assert index.query_subsets({"a", "b"}) == ["x", "y"]


def test_empty_index_returns_nothing() -> None:
    index = SetTrieIndex()
    assert index.query_subsets({"a"}) == []
    assert index.query_supersets(set()) == []


# --------------------------------------------------------------- benchmark


def _benchmark(n_items: int = 2000, n_queries: int = 200) -> tuple[float, int]:
    """Mean nodes_visited per subset query vs total items (speedup gauge). Not an assert."""
    rng = random.Random(31337)
    items = _random_corpus(rng, n_items)
    index = SetTrieIndex(tuple(items))
    rng_q = random.Random(80085)
    total_visited = 0
    for _ in range(n_queries):
        index.query_subsets(_random_query(rng_q))
        total_visited += index.nodes_visited
    return total_visited / n_queries, n_items


def test_benchmark_reports_speedup() -> None:
    mean_visited, n_items = _benchmark()
    # Soft expectation: pruning keeps mean visited well under a full per-item scan.
    assert mean_visited < n_items
    print(f"\n[set-trie benchmark] mean nodes_visited={mean_visited:.1f} vs n_items={n_items}")


if __name__ == "__main__":
    mean_visited, n_items = _benchmark()
    print(f"mean nodes_visited per subset query: {mean_visited:.1f}  (n_items={n_items})")

"""Cluster-graph domain entities — the 2nd pipeline artifact (alongside the set-trie tree).

Built from the shared ``ConceptNode`` seed: a similarity graph over tag overlap, partitioned
into communities. Framework-agnostic and immutable — no networkx/louvain import here (those
live in adapters). Cycles are allowed: this is a clustering graph, never converted to a tree,
which is what avoids the cycle-breaking complexity that retired the old graph pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClusterEdge:
    """A weighted relation between two section nodes, with its audit basis."""

    source: str  # node section_id (source < target, lexicographically, for stability)
    target: str
    weight: float
    shared_tags: tuple[str, ...]  # the tags that justify the edge (auditable)


@dataclass(frozen=True)
class Community:
    """A detected cluster: its member section_ids plus the tags they share."""

    community_id: int
    members: tuple[str, ...]  # sorted section_ids
    shared_tags: tuple[str, ...]  # tags common to (most of) the members


@dataclass(frozen=True)
class ClusterGraph:
    """The full cluster artifact: edges + communities over the node seed."""

    edges: tuple[ClusterEdge, ...] = ()
    communities: tuple[Community, ...] = field(default_factory=tuple)

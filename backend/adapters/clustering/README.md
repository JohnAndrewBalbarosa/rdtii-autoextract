# `adapters/clustering/` — Concept-Graph Builders

Keeps `networkx` / `python-louvain` (both BSD) **out of the core.** Implements the
clustering ports. Deterministic: fixed seed, stable community IDs.

## Files

| File | Role | Port |
|---|---|---|
| `tag_overlap_scorer.py` | IDF-weighted Jaccard edges over `ConceptNode` tags (sparse via inverted index) | `SimilarityScorer` |
| `louvain_communities.py` | Louvain community detection, fixed seed, relabel by smallest member | `CommunityDetector` |

## Graph construction

```mermaid
flowchart LR
    N["ConceptNode[]<br/>(tags)"] --> INV["inverted index<br/>tag → nodes"]
    INV --> PAIRS["candidate pairs<br/>(share ≥1 tag)"]
    PAIRS --> SCORE["IDF-weighted Jaccard<br/>→ ClusterEdge[]"]
    SCORE --> LOU["Louvain modularity<br/>(seed fixed)"]
    LOU --> COM["Community[]<br/>stable IDs"]
    SCORE --> CG([ClusterGraph])
    COM --> CG
```

Orchestrated by `core/pipeline/cluster_pipeline.py`. Owned by **Department 02**
([pipeline-eval](../../../docs/departments/02-pipeline-eval/README.md)).

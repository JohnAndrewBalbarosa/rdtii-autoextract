# Concept-Graph Pipeline

> ⚠️ **SUPERSEDED (2026-06-20).** Stages 2–5 below (complete-graph edge weighting, θ-pruning,
> community detection, FCA hierarchy, PageRank) were **removed** in favour of a tags-only
> **`SetTrieIndex`** (`core/pipeline/set_trie.py`) — an acyclic-by-construction trie for fast
> tag matching with branch pruning. No edges, no edge weights, no θ, no cycles. Only the
> **tagging layer (Stage 0–1)** — captioning + multi-label tagging → `ConceptNode`
> (`core/domain/concept_node.py`, via `adapters/extraction/structural_extractor.py`) — survives,
> and its tagged nodes feed the set-trie. The rest of this file is kept for historical context.

> The second pipeline. After the extraction pipeline produces article-level findings,
> this layer turns law sections into a **connected concept graph** — Obsidian-style nodes
> that cross-tag and cluster — then induces a **generality hierarchy** over them.
>
> Stays framework-agnostic: every step is a port in `core/`, every model/library is a
> swappable adapter (R12, R16). Apache-2.0-compatible tooling only (R9, R13).

---

## Mental model

Each **law section is a node** carrying **one or more tags** (multi-label). Once everything
is scanned, the nodes are connected into a weighted graph where an **edge weight = strength
of relation** between two sections. Weak edges (below a threshold) are pruned, so the
surviving edges draw **topical borders** — how close one legal idea is to another. The
clusters that emerge are the groupings (like the Obsidian graph view). Finally a
PageRank-style pass plus a generality hierarchy turns the flat web into a navigable tree:
broad **entry-point** categories at the top, increasingly specific sub-topics deeper down.

The hierarchy follows the **denotative ↔ connotative** intuition exactly, and it has a
formal name: **Formal Concept Analysis (FCA)**.

- **Extent** (denotation) = the set of example sections a concept covers.
- **Intent** (connotation) = the set of tags describing it.
- **More tags (richer description) ⇒ fewer matching examples ⇒ deeper, more specific.**
- **Fewer tags (general) ⇒ more examples ⇒ shallower, an entry-point category.**

This is not a metaphor — it is the defining property of a concept lattice.

---

## The 5 stages

```
 OCR + captioning      retrieval+tagging      complete graph      prune below θ     community         hierarchy
 (SigLIP descriptor)──▶  (multi-label)   ──▶  + edge weights ──▶ (pseudo-determ.)──▶ detection  ──▶ (FCA + PageRank)
        │                     │                     │                   │               │                │
    Captioner             Tagger              EdgeScorer           GraphBuilder   CommunityDetector  HierarchyBuilder
   (the BASIS)         ConceptNode                                                                   + GraphRanker
```

### Stage 0/1a — OCR + SigLIP-style captioning (the basis)

This runs **up front**, during/right after retrieval and OCR — before any tag exists.
For each section we produce a **caption / descriptor**: a short, normalized description of
what the provision is about. For plain text this can be the OCR text itself; for **scanned,
non-English, or visually-laid-out documents** (R19) a **vision-language model captions the
section image directly** (the true SigLIP-lineage step), so we are not hostage to OCR noise.

**This caption is the BASIS for every tag in Stage 1** — the Tagger embeds and scores against
it, not against raw bytes. Garbage caption ⇒ garbage tags, so this step is first-class.

- **Port:** `Captioner.caption(raw_section, ocr_text, language) -> str`
- **Reference adapter:** `Qwen2-VL-2B` / `ColQwen2` (Apache 2.0 — *not* PaliGemma/ColPali,
  which carry the restrictive Gemma license). Falls back to OCR text on plain layouts.

### Stage 1 — Tagging → nodes

As a section's caption is produced it is tagged and immediately becomes a `ConceptNode`.
Tags are **multi-label** (a section can belong to Pillar 6 *and* 7, plus finer concept tags),
and are derived from **text + caption** together.

- **Port:** `Tagger.tag(section_id, text, caption, language) -> set[str]`
- **Reference adapter:** `BGE-M3` (MIT, multilingual) embeddings → sigmoid zero-shot
  scoring of the caption against tag/indicator label descriptions (SigLIP-style multi-label).
  Verify with `bge-reranker-v2-m3` (Apache) or an LLM (R14). Few-shot tune with `SetFit` (Apache).

### Stage 2 — Complete graph + edge weighting (subtractive, not additive)

Conceptually start from a **complete graph** — every node potentially connected to every
other node — then **remove** edges that fail the threshold. The threshold is the **eraser,
not the glue**: edges below `θ` are dropped because they are not worth keeping, not because
we never built them. (In practice we never materialise the full N² edges — ANN top-K
candidates approximate the complete graph cheaply — but the *semantics* is subtractive.)

Once the candidate pairs exist, score them. Edge weight blends two signals:

```
w(a, b) = α · tag_overlap(a, b) + (1 − α) · cosine(emb_a, emb_b)
```

- `tag_overlap` = weighted Jaccard over tag sets (rare shared tags count more — IDF-weighted).
- `cosine` = embedding similarity from the vector store (HNSW/pgvector ANN to avoid a true
  O(n²) all-pairs scan; restrict candidates to top-K neighbours).
- **Port:** `EdgeScorer.score(a, b) -> float`

### Stage 3 — Threshold pruning (pseudo-deterministic)

Drop every edge with `w < θ`. Surviving edges define the topical **borders** / proximity.

**Pseudo-deterministic** means: given the same inputs, the same `θ`, fixed RNG seeds, and
sorted tie-breaking, the graph is **reproducible** byte-for-byte. This matters for the audit
view and for judges re-running on unseen jurisdictions (R6, R15).

- `θ` is **calibrated on the labelled RDTII data**, not guessed — pick the cutoff that
  maximises F1 against known relations (R20). Embedding/LLM scores are not probabilities, so
  calibrate; never hardcode `0.8`.
- Prefer **mutual top-k** over a single global cutoff: keep an edge only if each node is in
  the other's top-k. This kills "hub" nodes that connect to everything.
- **Port:** `GraphBuilder.build(nodes, edges) -> ConceptGraph` then `prune(graph, θ)`.

### Stage 4 — Community detection → groupings

Cluster the pruned graph into themes (the Obsidian-style groupings).

- **Reference:** Louvain / Leiden on edge weights, with a **fixed seed** for determinism.
- **Port:** `CommunityDetector.detect(graph) -> list[Community]`
- ⚠️ **License:** prefer **NetworkX** (BSD-3, Apache-compatible). `igraph`/`leidenalg` are
  **GPL** — avoid in an Apache repo, or isolate behind the adapter and document it. `python-louvain` is BSD.

### Stage 5 — Hierarchy induction (FCA) + PageRank ranking

> **Important shape note.** The hierarchy in 5a is *not* derived from the pruned graph edges.
> It is a **parallel derivation** from the same `ConceptNode[]`, using only the node × tag
> matrix. Concretely: the graph (Stages 2–4) and the lattice (Stage 5a) are two
> independent artifacts built from one shared seed of tagged nodes. Tweaking `θ` changes
> communities and PageRank scores; it does **not** change the lattice shape.
>
> ```
>                    ConceptNode[]  (the shared seed)
>                           │
>          ┌────────────────┴───────────────┐
>          ▼ (edges → prune θ)              ▼ (node × tag matrix)
>     ConceptGraph                     ConceptLattice
>     + Community[]                    (FCA generality tree)
>     + PageRank scores
> ```

Two complementary passes turn flat tagged nodes into a navigable tree.

1. **Generality hierarchy via FCA concept lattice.** Build (extent, intent) concepts from
   the node×tag matrix. The lattice orders concepts from general (many examples, few tags →
   **root / entry points**) to specific (few examples, many tags → **leaves**). This *is* the
   "main categories = the heavily-shared tags; deeper = more tags, fewer examples" structure
   you described.
   - **Port:** `HierarchyBuilder.build(nodes) -> ConceptLattice`
   - **Reference:** `concepts` library (MIT) for FCA.

2. **Within-graph importance via weighted PageRank** — not Google's web-link PageRank, but
   the same eigenvector-centrality model run on this concept graph. It scores which nodes are
   the influential hubs, and (via **Personalized PageRank** seeded from a chosen root) which
   nodes are "closest" to an entry point — exactly the "root node is just an entry point,
   then deeper levels are subcategories" navigation you want.
   - **Port:** `GraphRanker.rank(graph, seeds=None) -> dict[node_id, float]`
   - **Reference:** NetworkX `pagerank` (BSD).

> FCA gives the **tree shape** (specificity); PageRank gives the **ordering within a level**
> (which subcategory matters most). Together: an entry-point category opens into ranked
> subcategories, each into ranked sub-subcategories.

---

## How it plugs into the existing architecture

This is purely additive — new ports in `core/ports/graph.py`, new entities in
`core/domain/graph.py`. Nothing in `core/` imports a concrete graph library; NetworkX, FCA,
embeddings, and rerankers are all adapters. Swap any of them via config without touching the
domain (R12).

| Stage | Port | Reference adapter (license) |
| ----- | ---- | --------------------------- |
| 0/1a Captioning | `Captioner` | Qwen2-VL-2B / ColQwen2 (Apache); OCR-text fallback |
| 1 Tagging | `Tagger` | BGE-M3 (MIT) + bge-reranker-v2-m3 (Apache) |
| 2 Edge weight | `EdgeScorer` | weighted Jaccard + pgvector cosine |
| 3 Build/prune | `GraphBuilder` | NetworkX (BSD), calibrated θ |
| 4 Communities | `CommunityDetector` | Louvain/Leiden, fixed seed (mind GPL) |
| 5a Hierarchy | `HierarchyBuilder` | `concepts` FCA (MIT) |
| 5b Ranking | `GraphRanker` | NetworkX PageRank (BSD) |

## Determinism & auditability

- Fixed seeds + sorted tie-breaks + cached embeddings ⇒ reproducible graph (pseudo-deterministic).
- Every edge stores its **score + basis** (which shared tags, what cosine) so a reviewer can
  verify a connection in seconds (R6). No black-box edges.

## Deliberately deferred (YAGNI)

GNN link-prediction (e.g. GraphSAGE) could *learn* edges instead of scoring them by
similarity. Skip it until similarity + calibrated thresholds prove insufficient — an
explainable graph is far easier to defend to judges than a learned black box.

# Department 02 — Pipeline & Evaluation

**Mission:** Turn cleaned documents into tagged, indicator-mapped `Finding` rows, build
the concept graph, and **score everything against the golden dataset with a deterministic
F1 harness.** This is where accuracy is won or lost.

**Agent:** `zx-pipeline` · **Discipline:** the F1 harness is high-stakes — treat scoring
logic as if money rides on it. Determinism over cleverness.

---

## File structure (what this department owns)

```text
backend/core/domain/                      # Immutable domain entities (no frameworks)
├── entities.py            # Finding, Article, Pillar, ReviewStatus, DiscoveryTag
├── concept_node.py        # ConceptNode (tagged section, clustering seed)
├── cluster.py             # ClusterEdge, Community, ClusterGraph
├── document.py            # CrawledDocument, RawSection, DocumentGuide (shared w/ Dept 01)
├── access.py              # Access/compliance entities
├── indicator_codes.py     # 6.1 ⇄ P6-I1 code translation
└── indicator_definitions.py # CONCEPT_VOCAB + INDICATOR_TAGS (source of truth)

backend/core/pipeline/                    # Use cases (deterministic orchestration)
├── scoring.py             # ★ F1 harness: precision / recall / F1 vs gold
├── cluster_pipeline.py    # build_clusters → ClusterGraph → JSON
├── guided_tagging.py      # high-context guide + low-context section tagging
├── compliant_retrieval.py # policy-gated retrieval + audit
├── document_validator.py  # LLM-backed document validity check
├── set_trie.py            # Set-Trie subset/superset index (tags only, acyclic)
├── parallel_matcher.py    # parallel matching over the Set-Trie
└── ocr_cer.py             # OCR Character Error Rate harness (<5% target)

backend/adapters/extraction/              # ProvisionExtractor / tagger adapters
├── tagmatch_provision_extractor.py # ★ real substrate: tags → Set-Trie → indicators
├── structural_extractor.py   # Stage-1 heading-breadcrumb tagger
├── section_tagger.py         # breadcrumb + concept-vocab tagging
├── mock_provision_extractor.py # deterministic plumbing proof (real snippets)
├── fallback_provision_extractor.py # primary-then-fallback composition
└── text_helpers.py           # pure: title/section/clause derivation (real substrings)

backend/adapters/clustering/              # Graph adapters (networkx/louvain stay here)
├── tag_overlap_scorer.py  # IDF-weighted Jaccard edges (SimilarityScorer)
└── louvain_communities.py # deterministic Louvain (CommunityDetector, seed=42)

backend/adapters/llm/                     # The only swappable AI surface
├── router.py              # LLMRouter middleman (local | remote)
├── remote_provider.py     # Claude/GPT stub (wire API key here)
└── local_provider.py      # Ollama/self-hosted stub
```

---

## Modularity (functional breakdown)

### Module A — Domain (the vocabulary everyone agrees on)
Pure, immutable dataclasses. **`Finding`** carries the 6 mandatory fields + pillar +
indicator + confidence + review status. **`indicator_definitions`** is the *source of
truth*: `CONCEPT_VOCAB` (concept → trigger phrases) and `INDICATOR_TAGS` (indicator →
required concept set). Change accuracy here, not in a dozen extractors.

### Module B — Extraction (document → Findings)
A family of swappable `ProvisionExtractor` / `SectionExtractor` adapters, deliberately
ranked from real to plumbing-only:
- **`tagmatch_provision_extractor`** — the real deterministic substrate. Tags each section
  (`section_tagger`), queries the `set_trie` for indicators whose required tag-set is a
  **subset** of the section's tags, emits a `Finding` per match with a **real verbatim
  snippet**.
- **`structural_extractor` / `section_tagger`** — deterministic tagging from heading
  breadcrumbs + concept vocab (no AI).
- **`mock_provision_extractor`** — keyword-table plumbing proof; real snippets, no accuracy
  claim. Used as the safety net.
- **`fallback_provision_extractor`** — runs a primary extractor, falls back per-document if
  it yields nothing. (Default wiring in `run.py`: TagMatch → Mock.)

### Module C — Scoring & Evaluation (the keystone)
- **`scoring.py`** compares predicted `Finding`s against `GoldRecord`s (loaded by Dept 03's
  `golden_dataset`). A prediction is a **true positive** only if **country + pillar +
  indicator** match **and** (URL overlaps **or** act-name token-set Jaccard ≥ threshold).
  Emits `ScoreReport` (TP/FP/FN, precision, recall, F1, per-pillar). **No ML libs — token
  Jaccard only — byte-for-byte reproducible.**
- **`discovery_diff`** flags novel (NEW) predictions vs the reference baseline (R20).
- **`ocr_cer.py`** measures OCR Character Error Rate against the <5% target.

### Module D — Concept Graph / Clustering
The core architectural contribution. From `ConceptNode`s:
- **`tag_overlap_scorer`** builds IDF-weighted Jaccard **edges** (sparse via inverted
  index — no O(n²)). Implements `SimilarityScorer`.
- **`louvain_communities`** detects communities with a **fixed seed** for reproducibility,
  relabeled by smallest member for stable IDs. Implements `CommunityDetector`.
- **`cluster_pipeline`** orchestrates scorer + detector into a `ClusterGraph`, serializes
  to deterministic JSON, and surfaces **discovery candidates** (unmatched nodes inside
  matched communities) for human review.
- **`set_trie` + `parallel_matcher`** give fast subset/superset tag queries for matching at
  scale (acyclic, read-only, parallel-safe).

### Module E — LLM middleman (the only AI surface)
- **`LLMRouter`** routes every `complete()` call to an injected backend (`local` or
  `remote`) selected by env. The deterministic graph/scoring path **does not depend on it
  at all** — AI sits strictly behind this seam. `remote_provider`/`local_provider` are
  stubs to wire Claude/GPT or Ollama with a single config change.

---

## Port seams (the contract)

| Port (defined in Dept 03) | Relationship |
|---|---|
| `ProvisionExtractor` | **Implemented** by tagmatch / mock / fallback |
| `SectionExtractor`, `GuidedSectionTagger`, `TaggingReconciler` | **Implemented** by structural / guided tagging |
| `SimilarityScorer`, `CommunityDetector` | **Implemented** by clustering adapters |
| `LLMProvider` | **Implemented** by `LLMRouter` (+ provider stubs) |
| `CrawledDocument`/`ParsedDocument` (domain) | **Consumed** — handoff from Dept 01 |
| `GoldRecord` (via `golden_dataset`) | **Consumed** — ground truth from Dept 03 |

> Determinism contract: every default path (tag → extract → score → cluster) has fixed
> ordering, no RNG, no clock, no network. If a change makes a test non-reproducible, it is
> wrong by definition.

---

## Verify

```powershell
cd backend
python -m pytest -q tests/test_scoring.py tests/test_tagmatch_extractor.py `
  tests/test_mock_provision_extractor.py tests/test_structural_extractor.py `
  tests/test_clustering.py tests/test_set_trie.py tests/test_parallel_matcher.py `
  tests/test_guided_tagging.py tests/test_indicator_codes.py tests/test_ocr_cer.py
```

Honest scorecard: `python run_validation.py` (gold-vs-gold self-check must yield F1 = 1.0).

---

## Reverse-prompting hooks (task seeds for delegation)

1. **Raise F1 on an indicator** — *"Pillar 6 indicator P6-I2 is under-recalled. Within
   `indicator_definitions.py` adjust `CONCEPT_VOCAB`/`INDICATOR_TAGS`, and only if needed
   `tagmatch_provision_extractor.py`. Prove the gain with `run_validation.py` and
   `tests/test_scoring.py`. Do not weaken the match rule in `scoring.py`."*
2. **New extractor strategy** — *"Implement a `ProvisionExtractor` named `<x>` in
   `adapters/extraction/`. It must satisfy the port and pass a new test mirroring
   `tests/test_tagmatch_extractor.py`. Wire it via fallback, not by editing the port."*
3. **Graph tuning** — *"Calibrate the edge threshold θ in `tag_overlap_scorer.py` /
   `cluster_pipeline.py` for tighter communities. Keep Louvain seed fixed; output must stay
   reproducible (`tests/test_clustering.py`)."*
4. **Wire a real LLM** — *"Implement `remote_provider.py` for Claude via the `LLMProvider`
   port. `LLMRouter.from_env()` must select it on `ZETARIX_LLM_BACKEND=remote`. The
   deterministic scoring path must remain green with the LLM absent."*

**Boundary reminder:** edit only `core/domain/`, `core/pipeline/` (except
`output_emitter.py` / `golden_dataset.py` — Dept 03), and `adapters/{extraction,clustering,llm}/`.
Never change a signature in `core/ports/`.

# Project Proposal

## Global Hackathon on Using AI for Digital Trade Regulatory Analysis
**UN ESCAP & KMITL | 2026**

---

## 1. Project Title

**Zetarix** — An Open-Source AI Pipeline for Automated Digital Trade Regulatory
Analysis Across Asia-Pacific Jurisdictions (for the UN ESCAP RDTII — Regional Digital
Trade Integration Index).

---

## 2. Problem Statement

The RDTII workflow currently requires ESCAP researchers to manually search government
portals, retrieve regulatory documents, read legal text, and extract structured data at
article-level granularity across multiple Asia-Pacific jurisdictions. This process is
time-intensive, difficult to scale, and dependent on researcher availability and language
coverage.

The target of this project is to automate 80% of that pipeline — specifically the search,
retrieve, and describe stages — for RDTII Pillars 6 (Cross-Border Data Flows) and 7
(Domestic Data Protection), while preserving a transparent, non-technical human review step
for the remaining 20%.

---

## 3. Objectives

- Automate regulatory document discovery beyond the existing ESCAP RDTII database
- Achieve article-level extraction with all 6 mandatory fields: title, last update, URL,
  scope, provisions, impact
- Map extracted provisions to Pillar 6 and 7 sub-indicators with traceable citations
- Deliver a self-hostable, open-source tool deployable without proprietary infrastructure
- Design all LLM components to be modularly swappable to open-weight models (Llama 3 family)
- Provide a non-technical human review UI where any mapping can be verified or rejected in seconds

---

## 4. System Architecture

The system is built on **ports & adapters (hexagonal) architecture**: the core domain
depends only on interfaces, and **every AI model named below is a swappable suggestion**, not
a hardcoded choice. The system is **model-agnostic** — any LLM, OCR engine, embedding model,
or graph library can be swapped via config without touching the domain. Concrete models are
disclosed in the Technical Memo. See [ARCHITECTURE.md](../backend/docs/ARCHITECTURE.md) and
[GRAPH_PIPELINE.md](../backend/docs/GRAPH_PIPELINE.md).

The pipeline runs in five stages: the first four cover discovery → describe; the fifth turns
the described provisions into a **connected concept graph** for cross-tagging and navigation.

### Stage 1 — Discovery & Retrieval

**Goal:** Locate regulatory documents relevant to Pillars 6 and 7 across target Asia-Pacific
jurisdictions, including documents not currently in the ESCAP database.

**Components:**
- Web crawler targeting national legislation portals, official gazette archives, ministry
  websites, and legal databases _(suggested: Playwright + BeautifulSoup)_
- Messy portal handling: rate-limiting, rotating user-agents, fallback to web archive sources
- Language detection routing non-English documents to the translation step
- Provenance metadata per document: URL, retrieval timestamp, country, language, source portal

**Output:** Raw document queue with full provenance.

### Stage 2 — OCR & SigLIP-style Captioning

**Goal:** Convert all document formats to clean, machine-readable text at <5% Character Error
Rate, and produce a **caption/descriptor per section that becomes the basis for tagging**.

**Components:**
- PDF classifier distinguishing text-layer PDFs from scanned images
- OCR with image preprocessing (deskew, binarization, contrast); fallback engine for
  Southeast Asian scripts _(suggested: Tesseract 5 + OpenCV, PaddleOCR fallback)_
- **SigLIP-style captioning up front:** for scanned, non-English, or visually-laid-out
  documents, a vision-language model captions the section image directly, so tags are not
  hostage to OCR noise _(suggested: Qwen2-VL / ColQwen2 — Apache-2.0, not the Gemma-licensed
  PaliGemma)_. The caption is the **basis for all downstream tags.**
- Non-English text routed through open-weight translation _(suggested: Helsinki-NLP/opus-mt)_
- Article-level chunking via structural parsing (article/section/clause boundaries) — chunks
  are the atomic unit; document-level summaries are explicitly rejected

**Output:** Article-level chunks, each with OCR text + caption + structural metadata.

### Stage 3 — Tagging & Extraction

**Goal:** Multi-label tag every section, extract all 6 mandatory fields, and map provisions to
Pillar 6/7 sub-indicators with verifiable citations.

**Components:**
- Multi-label tagging (SigLIP-style sigmoid scoring of the caption against indicator label
  descriptions — a section may carry Pillar 6 *and* 7 plus finer tags) _(suggested embeddings:
  BGE-M3 multilingual; verify with a reranker or LLM)_
- RAG-based field extraction: retrieved chunks → LLM with strict JSON schema enforcing all 6
  fields + source citation _(suggested vector store: pgvector / Chroma — both self-hostable)_
- Confidence scoring per record
- **LLM provider abstraction:** every LLM call goes through one interface. Dev uses a paid
  API _(suggested: Claude / GPT)_; production resolves to open-weight _(suggested: Llama 3.1
  via Ollama)_ with a single config change — no code edits.

**Output:** Structured records per article (6 fields, tags, sub-indicator mapping, confidence,
source reference) — each record is also a **node** for Stage 5.

### Stage 4 — Human Review Interface

**Goal:** Enable non-technical ESCAP researchers to verify, reject, or edit any mapping in
seconds.

**Components:**
- Table-based review UI: each row is one extracted article mapping with all 6 fields inline
- Per-row actions: Accept / Reject / Edit — rejected rows re-enter the queue flagged for
  manual completion
- Audit view: each record links to the exact source page, article number, and highlighted
  text span in the original document
- Export: CSV/Excel for researchers, JSON downstream
- The human review step is the primary UI entry point — not a secondary screen

**Output:** Human-verified findings.

### Stage 5 — Concept-Graph Construction

**Goal:** Connect the tagged sections into a weighted concept graph so related provisions
cross-link, cluster, and become navigable — the core architectural contribution.

**Components:**
- Edge weighting between nodes: tag overlap (IDF-weighted) + embedding cosine similarity
- **Pseudo-deterministic threshold pruning:** edges below a calibrated θ are removed;
  surviving edges define topical borders (reproducible given fixed seeds + θ)
- Community detection for Obsidian-style groupings _(suggested: NetworkX/Louvain — BSD;
  avoid GPL `leidenalg`/`igraph` in an Apache repo)_
- **Generality hierarchy via Formal Concept Analysis** (intent = tags, extent = examples:
  more tags ⇒ fewer, more specific examples) + **weighted PageRank** for entry-point ranking
  and within-level ordering

**Output:** A navigable concept graph: broad entry-point categories → ranked specific
sub-topics. Full design in [GRAPH_PIPELINE.md](../backend/docs/GRAPH_PIPELINE.md).

---

## 5. Tech Stack

**The system is model-agnostic.** Each layer below sits behind a port (interface); the named
models/libraries are **suggested reference adapters**, swappable via config without code
changes. This swappability is itself heavily scored (20 pts Stage 1 + 20 pts Stage 3).

| Layer (port) | Suggested adapter (dev) | Suggested open-weight target |
|---|---|---|
| LLM (`LLMProvider`) | Claude / GPT | Llama 3.1 8B/70B via Ollama |
| Captioning (`Captioner`) | Qwen2-VL / ColQwen2 (Apache) | Same; OCR-text fallback |
| Embeddings (`Tagger`) | BGE-M3 (multilingual, MIT) | Same |
| OCR (`OCREngine`) | Tesseract 5 + OpenCV / PaddleOCR | Same |
| Vector store (`VectorStore`) | pgvector / Chroma (self-hostable) | Same |
| Crawler (`DocumentSource`) | Playwright + BeautifulSoup | Same |
| Translation | Helsinki-NLP/opus-mt | Same |
| Graph + ranking (`GraphBuilder`/`GraphRanker`) | NetworkX (BSD) + FCA `concepts` (MIT) | Same |
| Backend | FastAPI (Python) | Same |
| Frontend | React / Next.js | Same |
| Deployment | Docker + docker-compose | Same |
| License | All components Apache-2.0-compatible | — |

All reused open-source components will be disclosed in the Technical Memo with license
verification. Models above are starting suggestions, not commitments.

---

## 6. Coverage & Generalization

**Application stage:** Tool demonstrated on publicly available RDTII-adjacent documents
across at least 3 Asia-Pacific countries, including at least one non-English jurisdiction.

**Round 1:** Evaluated against 5–10 documents from 3 provided countries using the reference
taxonomy from the Resource Library.

**Finale readiness:** Architecture designed to handle 10 assigned countries with no
retraining. Non-English documents handled via the translation pipeline. Scanned PDFs with
<5% CER handled via the OCR pipeline. Messy portals handled via Playwright with fallback
strategies. Minimum delivery target: 3 countries under live stress test conditions.

---

## 7. Originality & Innovation

The primary contribution is not a novel model architecture — it is a complete, deployable,
end-to-end pipeline purpose-built for the RDTII legal extraction task that currently does not
exist in open-source form.

Specific contributions:
- Article-level chunking strategy tuned for Asia-Pacific legal document structure
- Fine-tuned classifier for Pillar 6/7 sub-indicator mapping using RDTII taxonomy as training
  signal
- Provider-agnostic LLM abstraction enabling full open-weight deployment
- Human review UI designed specifically for non-technical policy researchers

All components that are reused (pre-trained models, libraries, frameworks) will be disclosed
in the Technical Memo with clear delineation of original development.

---

## 8. Sustainability & Cost

**Self-hostable:** The full pipeline runs via Docker on commodity hardware. No proprietary
API dependency in production deployment.

**Cost estimate (open-weight configuration):** For a 50-page regulatory document, estimated
processing cost is approximately USD 0.00 in API fees when running Llama 3.1 8B locally.
Compute cost on a standard cloud GPU instance (e.g., 4× A10G) is approximately USD 0.05–0.10
per document at batch processing rates.

**Cost estimate (API configuration):** At Claude Sonnet pricing with article-level chunking
and ~200 chunks per 50-page document, estimated cost is approximately USD 0.10–0.25 per
document.

Exact cost benchmarks will be reported in the Technical Memo after empirical testing.

**Maintenance:** Modular architecture allows individual components (OCR engine, LLM provider,
vector DB) to be upgraded independently. Fine-tuned classifier weights and training data will
be published in the GitHub repository.

---

## 9. Licensing & IP

The final tool will be released under the Apache License 2.0 as required. All team members
retain copyright to their original contributions while granting the perpetual, worldwide,
irrevocable license specified under Apache 2.0. All reused components are Apache-2.0-compatible.
Fine-tuned model weights will be published in the GitHub repository. Training data and
fine-tuning methodology will be disclosed in the Technical Memo.

---

## 10. Team

| Role | Responsibility |
|---|---|
| Technical Lead | AI architecture, OCR pipeline, RAG system, LLM abstraction layer, Docker deployment |
| Substantive Lead | Pillar 6/7 legal/policy mapping, output accuracy validation, RDTII taxonomy interpretation, Technical Memo legal rationale |

Both roles will be held by named team members with demonstrated competency verified at Stage
1 application. If applicable, faculty participation will be designated as either full member
or advisor — not both.

---

## 11. Key Milestones

| Date | Milestone |
|---|---|
| 25 May 2026 | Application submitted (CVs, Concept Video, Technical Memo, Declaration) |
| 31 May 2026 | Shortlist announcement |
| 5–10 June 2026 | ESCAP & KMITL training workshops |
| 20 July 2026 | Round 1 submission — tool evaluated on 3 provided countries |
| 31 July 2026 | Hybrid pitch |
| 1 August 2026 | Finalists announced |
| 30 September 2026 | Final submission |
| 15 October 2026 | Award ceremony, Bangkok |

---

## 12. Contact & Repository

**Organizers:** escap-digitaltrade-hackathon@un.org | regtech2026@kmitl.ac.th
**RDTII Framework:** https://www.unescap.org/projects/rcdtra/coverage
**RDTII Guide:** https://www.unescap.org/kp/2025/regional-digital-trade-integration-index-rdtii-21-guide
**Project repository:** *(to be published under Apache 2.0 upon submission)*

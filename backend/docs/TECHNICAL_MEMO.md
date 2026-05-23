# Technical Memo — RDTII AutoExtract

*Global Hackathon on AI for Digital Trade Regulatory Analysis (UN ESCAP & KMITL, 2026). Apache 2.0.*
*≤ 2 pages; diagrams count. Cost figures are preliminary estimates, to be finalized after empirical testing.*

**Problem.** Automate ~80% of the RDTII workflow (discover → describe) for **Pillar 6 (Cross-border
Data Flows)** and **Pillar 7 (Domestic Data Protection)** at article-level granularity, leaving a
transparent 20% human-review step. **Model-agnostic by design** — every model below is a swappable
suggestion behind a port, not a commitment.

## Pipeline

```
┌──────────┐   ┌───────────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐
│ 1 DISCOVER│──▶│ 2 OCR + SigLIP CAPTION │──▶│ 3 TAG+EXTRACT │──▶│ 4 HUMAN REVIEW│──▶│ 5 CONCEPT GRAPH    │
│ crawl,    │   │ <5% CER; caption =     │   │ multi-label   │   │ accept/reject │   │ weighted edges →   │
│ anti-bot, │   │ BASIS for tags; VLM    │   │ + 6 fields +  │   │ /edit; audit  │   │ prune(θ) →         │
│ provenance│   │ on scanned/non-EN docs │   │ indicator map │   │ view, export  │   │ community → FCA+PR │
└──────────┘   └───────────────────────┘   └──────────────┘   └──────────────┘   └───────────────────┘
   DocumentSource      OCREngine/Captioner       Tagger/LLM         FindingRepo      GraphBuilder/Ranker
```

**6 mandatory fields per article:** `title · last_update · url · scope · provisions · impact`
(+ pillar, indicator, confidence, review_status). Document-level summaries are rejected.

**Stage 5 (core contribution):** tagged sections become nodes; edges = IDF-weighted tag overlap +
embedding cosine; edges below a **calibrated θ** are pruned (pseudo-deterministic — fixed seeds + θ ⇒
reproducible). Community detection yields Obsidian-style groupings; a **Formal Concept Analysis**
lattice (intent = tags, extent = examples → more tags ⇒ fewer, more specific examples) plus weighted
**PageRank** turns the web into navigable entry-point → sub-topic hierarchy.

## Architecture — ports & adapters (swappability is scored: 20 pts S1 + 20 pts S3)

The core domain imports no framework or model SDK; concrete tools are config-selected adapters.

| Port | Suggested adapter (dev) | Open-weight target | License |
|---|---|---|---|
| `DocumentSource` | Playwright + BeautifulSoup | same | BSD/MIT |
| `OCREngine` | Tesseract 5 + OpenCV / PaddleOCR | same | Apache-2.0 |
| `Captioner` | Qwen2-VL / ColQwen2 (vision-language) | same | Apache-2.0 |
| `Tagger` (embeddings) | BGE-M3 (multilingual) + reranker | same | MIT/Apache |
| `VectorStore` | pgvector / Chroma | same | PostgreSQL/Apache |
| `LLMProvider` | Claude / GPT | Llama 3.1 8B/70B via Ollama | Apache-compat |
| `GraphBuilder`/`GraphRanker` | NetworkX + FCA `concepts` | same | BSD/MIT |

> ⚠️ **License discipline:** prefer ColQwen2 over PaliGemma/ColPali (Gemma license); NetworkX/Louvain
> over GPL `leidenalg`/`igraph`; avoid CC-BY-NC models (e.g. Jina v3). All reused components are
> Apache-2.0-compatible and disclosed here; fine-tuned weights ship in the repo.

## Cost per 50-page document *(preliminary — pending empirical test)*

Assumption: ~200 article-level chunks / 50-page doc.

| Configuration | OCR + caption | Extraction + verify (LLM) | Graph | **Total / 50 pp** |
|---|---|---|---|---|
| Open-weight (Llama 3.1 8B, self-host GPU) | compute only | compute only | negligible | **~USD 0.05–0.10** (API: $0.00) |
| API (Claude/GPT) | n/a | dominant cost | negligible | **~USD 0.10–0.25** |

Open-weight compute basis: a standard cloud GPU (e.g. A10G-class) at batch rates. Exact CER, latency,
and per-doc cost benchmarks reported after testing on the provided countries.

## Generalisation, fine-tuning, originality

- **Generalisation:** no per-country retraining; non-English via captioning + translation, scanned
  PDFs via OCR (<5% CER), anti-bot portals via headless browser + archive fallback. Target ≥3 of 10
  assigned countries at finale.
- **Fine-tuning *(planned, pending labelled data)*:** few-shot tune a small encoder/classifier for
  Pillar 6/7 sub-indicators using the RDTII taxonomy as signal; θ calibrated on RDTII labelled data
  (F1-optimal, not guessed). Base model, data, and method disclosed; weights published in the repo.
- **Originality:** not a new model — a complete, deployable, open-source RDTII pipeline that does not
  yet exist, with a concept-graph layer for cross-jurisdiction evidence discovery.

**Deploy:** `docker-compose up` → api + web + Postgres/pgvector. Self-hostable, no proprietary
production dependency. Full design: `docs/ARCHITECTURE.md`, `docs/GRAPH_PIPELINE.md`.

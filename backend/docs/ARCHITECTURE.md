# RDTII AutoExtract Production Architecture

RDTII AutoExtract is a regulatory-intelligence platform for the UN ESCAP Digital Trade
Regulatory Integration Index. Its production goal is to automate 80-90% of public legal
evidence discovery, retrieval, extraction, and indicator mapping while preserving human
review as the final authority.

The system is not a generic scraper. It is a supervised, auditable AI pipeline that
discovers authoritative legal sources, navigates complex government portals, retrieves
source documents, extracts citation-backed evidence, and improves from reviewer feedback.

## 1. High-Level Architecture

The production architecture keeps the existing ports-and-adapters principle:

```text
Next.js reviewer console
        |
        | HTTP/OpenAPI
        v
FastAPI API adapter
        |
        | starts/reads workflows
        v
Workflow orchestration layer
        |
        | calls pure services through ports
        v
Domain + orchestration services
        |
        | adapter interfaces
        v
Playwright / HTTP / OCR / parsers / vector DB / local LLMs / storage
```

Current repository mapping:

- `frontend/`: reviewer console.
- `backend/src/zetarix/app/`: FastAPI adapter.
- `backend/src/zetarix/orchestration/`: workflow-facing application services.
- `backend/src/zetarix/domain/`: domain entities and taxonomy.
- `backend/src/zetarix/transport/`: HTTP, Playwright, proxy, PDF transport.
- `backend/src/zetarix/crawling/`: adaptive crawl and layout-learning logic.
- `backend/src/zetarix/extraction/`: legal interpretation and finding extraction.
- `backend/src/zetarix/inference/`: few-shot/RAG grounding.
- `backend/src/zetarix/training/` and `backend/src/zetarix/pretrain/`: feedback, data, eval, and adapter export.

Production service components:

| Component | Responsibility | Preferred stack |
| --- | --- | --- |
| API | User-facing commands, review, exports, admin | FastAPI, Pydantic |
| Workflow engine | Durable long-running crawl/extract/retrain jobs | Temporal Python |
| Browser workers | Dynamic portal navigation and downloads | Playwright |
| Retrieval workers | HTTP/PDF/DOCX/API fetch and source versioning | Python async + adapters |
| Parsing/OCR workers | HTML/PDF/DOCX/OCR/table extraction | BeautifulSoup/lxml, pypdf, Tesseract/PaddleOCR/docTR |
| AI workers | extraction, validation, routing, reranking | local LLM router, vLLM/Ollama/llama.cpp |
| Metadata DB | jobs, documents, findings, audit trail | PostgreSQL |
| Vector DB | chunk retrieval and RAG | Qdrant production, pgvector fallback |
| Object storage | raw artifacts and exports | MinIO/S3 |
| Web UI | review, document viewer, analytics | Next.js, React, TypeScript |

## 2. End-to-End Data Flow

1. **Run creation**
   - User or scheduled job creates a run with jurisdiction, pillar(s), optional seed URLs, source policy, and crawl limits.
   - API stores run metadata and starts a durable workflow.

2. **Discovery**
   - Discovery service searches official government, regulator, parliament, gazette, and legal repository domains.
   - Candidates are scored for authority, jurisdiction match, source type, recency, and legal relevance.
   - Output: `SourceCandidate[]` with score, reason, evidence URL, and source owner.

3. **Navigation**
   - Playwright navigation worker opens candidate portals and follows bounded, structured actions.
   - The worker records screenshots, DOM snapshots, network events, downloads, and action traces.
   - Output: retrieval targets such as HTML pages, PDFs, document-library records, API endpoints, and amendment pages.

4. **Retrieval and versioning**
   - Retrieval workers fetch artifacts, preserve raw bytes, compute content hashes, and store originals in object storage.
   - Document versions are linked to source authority, effective date, amendment status, repeal status, and retrieval time.

5. **Parsing and normalization**
   - HTML is cleaned and structurally parsed.
   - PDFs are text-extracted when digital and OCRed when scanned.
   - DOCX, tables, section headings, article numbers, citations, and cross-references are normalized.
   - Output: article/section chunks with source offsets, page coordinates, language, and metadata.

6. **Indexing**
   - Chunks are embedded and indexed with dense vectors, sparse/keyword signals, and metadata filters.
   - The original verbatim text remains the evidence source; generated summaries are never treated as ground truth.

7. **RAG and extraction**
   - Retrieval finds candidate chunks per pillar/indicator.
   - Reranking selects the strongest legal evidence.
   - Legal extraction emits structured findings with citation span IDs, confidence factors, and rationale.

8. **Validation**
   - Validator checks that every generated claim is supported by exact source text.
   - Unsupported mappings are rejected or sent to review as low-confidence.

9. **Review and feedback**
   - Reviewers approve, reject, or modify findings.
   - Decisions append to training data and audit logs.
   - Verified findings become future few-shot exemplars and fine-tuning candidates.

## 3. AI Pipeline

The AI pipeline is stage-specific rather than one monolithic agent:

| Stage | Input | Output | Model use |
| --- | --- | --- | --- |
| Source classification | URL, page title, snippet, domain | source authority score | small local LLM or classifier |
| Link relevance | anchor text, surrounding DOM, current goal | ranked links/actions | small local LLM + heuristics |
| Layout learning | sampled DOM skeleton | extraction selectors/rules | LLM once per layout |
| Legal interpretation | article text + metadata | obligation type, scope, triggers, summary | grounded legal LLM |
| Indicator tagging | interpretation + precedent tags | RDTII indicators + rationale | grounded legal LLM |
| Evidence validation | finding + source chunks | pass/fail, confidence factors | deterministic checks + LLM judge |
| Reviewer assistance | finding + source | explanation and correction suggestions | local LLM |

Hard rule: generated outputs must cite exact source spans. If no source span exists, no production finding is emitted.

## 4. Multi-Agent Workflow

Agents communicate through structured artifacts persisted by the workflow engine. They do not pass free-form chat history as the system of record.

| Agent | Responsibility | Structured output |
| --- | --- | --- |
| Discovery Agent | Find official legal sources and rank authority | `SourceCandidate[]` |
| Navigation Agent | Use Playwright to reach documents | `NavigationTrace`, `RetrievalTarget[]` |
| Retrieval Agent | Fetch and version source artifacts | `DocumentVersion` |
| OCR/Parsing Agent | Convert artifacts into normalized chunks | `ParsedDocument`, `ArticleChunk[]` |
| RAG Agent | Retrieve/rerank candidate evidence | `EvidenceBundle[]` |
| Legal Extraction Agent | Produce legal interpretation and indicator tags | `FindingDraft[]` |
| Validation Agent | Check citation support and source currentness | `ValidationResult[]` |
| Confidence Agent | Combine quality signals into reviewer priority | `ConfidenceBreakdown` |
| Reviewer Assistant | Help humans inspect, modify, and explain findings | UI-only suggestions |

Recovery rules:

- Every agent activity is idempotent and restartable.
- Browser actions have bounded step budgets and loop detection.
- Failed documents are quarantined with reason codes, not dropped silently.
- Fallback order is deterministic parser -> OCR -> low-confidence review queue.

## 5. Playwright Autonomous Navigation

Playwright is the browser automation engine for dynamic government portals. The Navigation Agent operates with a controlled action space:

- `click`, `fill`, `select`, `press`, `expand`, `paginate`, `download`, `open_tab`, `backtrack`, `stop`.
- Observations include URL, DOM snapshot, visible text, forms, buttons, links, downloads, screenshots, and network responses.
- Actions are ranked by legal relevance, authority signals, text similarity to pillar goals, and portal-specific scaffolds.
- Per-domain site profiles store learned selectors, search-form behavior, pagination patterns, and blocked-path rules.

Stop conditions:

- Target legal document found.
- Newer consolidated version found.
- Repeated navigation loop detected.
- Step/time budget exceeded.
- Access is blocked or requires non-public authentication.

Compliance boundaries:

- Retrieve public legal sources only.
- Respect per-domain rate limits and configured crawl policies.
- Do not bypass authentication, paywalls, or CAPTCHA gates.

## 6. RAG Architecture

Retrieval is metadata-aware and citation-first.

Chunking:

- Primary unit: law -> part -> division -> section/article -> subsection/table row.
- Preserve hierarchy, heading, page number, source URL, text offsets, OCR confidence, language, and document hash.
- Tables are stored both as markdown/text and structured cells where possible.

Indexing:

- Dense multilingual embeddings for semantic similarity.
- Sparse/keyword retrieval for legal terms, article numbers, and exact phrases.
- Metadata filters for jurisdiction, pillar, issuing body, law status, date, source type, and language.
- Cross-encoder reranking before generation.

Grounding:

- Every extracted field that claims legal substance must reference one or more citation spans.
- The validator confirms quoted text exists in the source chunk and that offsets/page references are valid.
- The reviewer UI displays highlighted evidence side-by-side with the finding.

Confidence scoring combines:

- Source authority and currentness.
- OCR quality and parser confidence.
- Retrieval/rerank score.
- Indicator mapping confidence.
- Citation validation result.
- Similarity to verified precedent examples.

## 7. Local LLM Serving

The platform is local-first for privacy, cost control, reproducibility, and offline deployment.

Serving tiers:

| Tier | Use | Backend |
| --- | --- | --- |
| Developer local | Simple model runs and demos | Ollama |
| Production GPU | Throughput, batching, OpenAI-compatible serving | vLLM |
| CPU/offline fallback | Quantized GGUF models | llama.cpp |
| Manual experimentation | Developer desktop testing | LM Studio |

Recommended evaluation candidates:

- Qwen 2.5/3 Instruct for structured extraction and multilingual legal text.
- Llama 3.x Instruct for general reasoning and local availability.
- Mistral and Gemma for smaller/faster tasks.
- DeepSeek distill/reasoning variants where license and deployment constraints allow.

Model routing:

- Small/fast model: source/link classification and navigation ranking.
- Strong legal model: law interpretation, indicator tagging, reviewer assistant.
- Embedding model: multilingual legal chunk embeddings.
- Reranker: cross-encoder reranking of retrieved chunks.

Production requirements:

- Quantization support: GGUF, AWQ, GPTQ where appropriate.
- GPU acceleration with CPU fallback.
- Health checks before selecting an LLM extractor.
- Automatic fallback to deterministic extraction or review queue when no model is available.
- Model/version recorded on every finding.

## 8. Fine-Tuning And Continuous Learning

Few-shot/RAG grounding remains the default until there is enough high-quality reviewed data. Fine-tuning is promoted only when held-out evaluation beats the grounded baseline.

Training sources:

- Verified reviewer approvals.
- Reviewer corrections.
- Rejected findings as hard negatives.
- ESCAP gold-standard workbooks.
- Historical extraction runs with final human status.

Dataset schema:

```json
{
  "task": "law_interpreter | tag_generator | validator",
  "jurisdiction": "Singapore",
  "pillar": 6,
  "source_document_id": "...",
  "input": "...",
  "expected_output": {},
  "citation_spans": [],
  "review_status": "verified | rejected | modified",
  "model_version": "...",
  "dataset_version": "..."
}
```

Fine-tuning policy:

- Use LoRA/QLoRA/PEFT adapters, not full fine-tuning.
- Train separate adapters for legal interpretation and indicator tagging.
- Use frozen train/val/test splits stratified by jurisdiction and pillar.
- Prevent catastrophic forgetting with replay sets from previous jurisdictions and pillars.
- Promote adapters only after precision/recall/F1 and citation-validity improve over few-shot/RAG.

Continuous learning loop:

1. Review action is written to audit log.
2. Training example is derived and validated.
3. Dataset version is rebuilt.
4. Eval harness compares zero-shot, few-shot/RAG, and adapter-backed runs.
5. Passing adapters are exported and registered for local serving.

## 9. Database And Storage Recommendations

PostgreSQL stores durable metadata and audit records:

- `jurisdictions`
- `source_sites`
- `crawl_runs`
- `navigation_steps`
- `documents`
- `document_versions`
- `document_assets`
- `chunks`
- `citations`
- `findings`
- `review_decisions`
- `training_examples`
- `model_runs`
- `eval_runs`
- `exports`
- `audit_events`

Qdrant stores chunk vectors and payload metadata for hybrid retrieval. pgvector remains acceptable for local demos or small deployments.

MinIO/S3 stores:

- Raw HTML, PDF, DOCX, images, and API payloads.
- Screenshots and Playwright traces.
- OCR page images and extracted text.
- Export files.
- Model artifacts and eval reports where appropriate.

## 10. API Design

Core production endpoints:

```text
POST   /runs                       Start discovery/extraction workflow
GET    /runs/{id}                  Run status, stage progress, metrics, errors
POST   /runs/{id}/cancel           Cancel a running workflow
GET    /findings                   List reviewer-ready findings
GET    /findings/{id}              Finding detail with citations and confidence
PATCH  /findings/{id}/review       Approve, reject, or modify a finding
GET    /documents/{id}             Document metadata and artifact links
GET    /documents/{id}/chunks      Parsed chunks and citation anchors
POST   /exports                    Generate CSV/JSON/XLSX export
GET    /exports/{id}               Download/status for export
POST   /training/rebuild-dataset   Rebuild training data from review log
POST   /training/evaluate          Run model/eval comparison
GET    /metrics                    Operational metrics
```

Current implemented bridge:

- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/findings`
- `POST /runs/{run_id}/cancel`
- `GET /findings`
- `POST /pipeline/extract`
- `/training/*`
- `/health`

The current bridge returns reviewer-ready findings using the shared pipeline service and persists synchronous run records through a replaceable JSON repository. This should evolve into Temporal-backed workflows and PostgreSQL persistence.

## 11. Reviewer Console

The reviewer console should support:

- Run dashboard with jurisdiction, pillar, source coverage, and stage progress.
- Document viewer for HTML/PDF/OCR text with highlighted citation spans.
- Side-by-side finding and source evidence.
- Confidence breakdown and validation warnings.
- Approve, reject, modify, and needs-source-check actions.
- Search/filter by country, pillar, indicator, law, status, confidence, source type, and reviewer.
- CSV/JSON/XLSX export.
- Reviewer analytics: throughput, agreement, corrections by indicator, model drift, and time saved.

## 12. Deployment And Operations

Local/demo deployment:

- Docker Compose.
- FastAPI API.
- Next.js frontend.
- PostgreSQL.
- Qdrant.
- MinIO.
- Temporal.
- Playwright workers.
- Ollama local model serving.

Production deployment:

- Kubernetes.
- Separate API, workflow, browser, OCR, AI, and export worker pools.
- vLLM model servers with GPU scheduling.
- PostgreSQL managed or self-hosted with backups.
- Qdrant cluster for retrieval.
- S3-compatible object storage.

Monitoring:

- OpenTelemetry traces across API, workflows, crawlers, parsers, LLM calls, and reviewers.
- Prometheus metrics and Grafana dashboards.
- Sentry for application exceptions.
- Structured logs with run IDs, document IDs, model IDs, and source URLs.

## 13. Security And Compliance

- Public legal sources only.
- No credential theft, CAPTCHA bypass, or private-data access.
- Domain-specific crawl limits and backoff.
- Secrets stored in environment/secret manager, never in code.
- RBAC for reviewers, admins, and service accounts.
- Signed URLs for source artifacts.
- Immutable audit trail for review decisions, exports, and model outputs.
- Every production finding must be traceable to exact source text.

## 14. Scalability And Failure Recovery

Scalability:

- Partition runs by jurisdiction, domain, and document.
- Use browser worker pools with domain-level throttling.
- Cache documents by content hash.
- Skip re-OCR and re-embedding unchanged document versions.
- Batch embeddings and LLM calls where supported.

Failure recovery:

- Use durable workflow retries for crawl, OCR, parse, index, extraction, and export.
- Make activities idempotent by document hash and run ID.
- Quarantine failed documents with reason codes.
- Maintain fallback chain: structured parser -> OCR -> review queue.
- Keep partial results when individual sources fail.

## 15. Roadmap

1. Move all shared CLI/API execution into `zetarix.orchestration.pipeline_service`.
2. Add persisted run management backed by PostgreSQL.
3. Add Qdrant + MinIO services to Docker Compose.
4. Add Playwright Navigation Agent with per-domain site profiles.
5. Add article-level chunk schema and citation span validation.
6. Add hybrid retrieval and reranking.
7. Upgrade reviewer console with document viewer and highlighted citations.
8. Add model registry, eval gates, and LoRA adapter promotion.
9. Add Temporal workflows and worker pools.
10. Add production observability and release dashboards.

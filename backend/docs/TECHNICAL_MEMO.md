# Technical Memo (≤ 2 pages — reviewers read first 2 only)

> Living draft. Reviewers read **only the first 2 pages**; diagrams count. Keep tight.

## 1. Problem & approach
RDTII analysts manually search → retrieve → describe digital-trade provisions. We automate
~80% of that with a **ports-and-adapters AI pipeline**: discover → retrieve → OCR → article-chunk
→ RAG extract → indicator-map → human-review queue. Mandatory Pillars 6 & 7; article-level output
with the 6 mandatory fields.

## 2. Why it generalises (the scored part)
Core domain depends only on interfaces. LLM, OCR, vector store, crawler are swappable adapters
(`LLM_PROVIDER=llama3` etc.). Same code runs on unseen jurisdictions and non-English/scanned docs.

## 3. Reused components (disclosure — Apache-2.0-compatible)
| Component | Use | License |
| --------- | --- | ------- |
| _TBD_ OCR engine | text extraction <5% CER | _TBD_ |
| _TBD_ vector store | RAG retrieval | _TBD_ |
| _TBD_ base LLM (open-weight target: Llama 3) | extraction/verification | _TBD_ |
| _TBD_ crawler/browser | discovery, anti-bot | _TBD_ |

## 4. Cost per 50-page document
| Stage | Tokens / compute | Est. cost |
| ----- | ---------------- | --------- |
| OCR | _TBD_ | _TBD_ |
| Extraction (LLM) | _TBD_ | _TBD_ |
| Verification | _TBD_ | _TBD_ |
| **Total / 50 pages** | | **_TBD_** |

## 5. Fine-tuning (if used)
Base model, training data, method, and published weights location — _TBD_.

## 6. Architecture diagram
See [ARCHITECTURE.md](ARCHITECTURE.md).

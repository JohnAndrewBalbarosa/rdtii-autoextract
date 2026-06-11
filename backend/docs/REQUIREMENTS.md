# Requirements — traced from the Q&A (28 Apr 2026)

Every requirement below cites the Q&A item it comes from, so nothing is invented.

## 1. Scope & users

| # | Requirement | Source |
| - | ----------- | ------ |
| R1 | Automate ~80% of the RDTII workflow (search · retrieve · describe); leave 20% for human validation. | 1.4 |
| R2 | Primary users = ESCAP RDTII researchers; secondary = ministry analysts. **Non-technical** (no code, no JSON). | 1.1 |
| R3 | The 20% human-review step must be an **obvious UI surface**, not buried. | 1.1 |
| R4 | **Article-level granularity** — each output points to a specific article in a specific document. | 1.2 |
| R5 | Each finding carries **6 mandatory fields**: title, last_update, url, scope, provisions, impact. | 1.2 |
| R6 | A reviewer must verify/reject any mapping **in seconds**. Document-level summaries fail Stage 2. | 1.2 |
| R7 | **Mandatory pillars: 6 (Cross-border Data Flows) + 7 (Domestic Data Protection).** Bonus = scale to more pillars. | 1.3, 1.4 |
| R8 | Prove it works for **multiple Asia-Pacific countries**. | 1.4, 5.4 |

## 2. Licensing & originality

| # | Requirement | Source |
| - | ----------- | ------ |
| R9 | Final repo ships **Apache 2.0**. All reused components must be Apache-2.0-compatible. | 2.1, 2.4 |
| R10 | Build on prior work OK; submitting unchanged is not. Show meaningful new development. | 2.2 |
| R11 | Disclose **all** reused components in the Technical Memo. | 2.1 |

## 3. Architecture & swappability (heavily scored)

| # | Requirement | Source |
| - | ----------- | ------ |
| R12 | Dev may use paid LLM APIs (Claude/GPT/Gemini), **but design must be modularly swappable to open-weight models (e.g. Llama 3)**. 20 pts Stage 1 + 20 pts Stage 3. | 5.1 |
| R13 | Fine-tuning open-weight models allowed; published weights become part of submission (in repo, not private). Base license Apache-2.0-compatible. | 5.2 |
| R14 | Recommended pattern: **RAG over OCR'd legal text + article-level chunking + structured citation extraction + small classifiers w/ LLM verification.** | 5.3 |
| R15 | Practicality dominates (~70% of Stage 3 = deployment, interface, generalisation, live stress test). Optimise for "works, cheaply, repeatably, on unseen jurisdictions". | 2.3 |

## 4. Technical / deployment requirements

| # | Requirement | Source |
| - | ----------- | ------ |
| R16 | **Open-source, modular, self-hostable.** | 5.4 |
| R17 | **OCR < 5% CER.** | 5.4 |
| R18 | **Audit view** for human verification. | 5.4 |
| R19 | Must handle **non-English text, scanned PDFs, compliant access handling / messy portals** (Finale). | 5.4 |
| R20 | Prove discovery of **new evidence** beyond the provided RDTII DB/guide (20 pts Stage 2). | 5.4, 2.3 |
| R21 | **Cost estimate per 50-page document** must be documented (in Memo). | 4.3 |

## 5. Data / coverage milestones

| Stage | Coverage | Source |
| ----- | -------- | ------ |
| Application | Use ESCAP RDTII DB + guide to train/test; no fixed country set. | 5.4 |
| Round 1 (20 Jul) | 5–10 docs from **3 provided countries** + reference taxonomy. | 5.4 |
| Finale (30 Sep) | **10 assigned countries** (some non-English, messy) — deliver for **≥3**. | 5.4 |

## 6. Key dates

| Milestone | Date |
| --------- | ---- |
| Application deadline | **25 May 2026, 16:00 BKK / 09:00 UTC** |
| Shortlist | 31 May 2026 |
| Round 1 submission | 20 Jul 2026 |
| Hybrid pitch | 31 Jul 2026 |
| Finalists announced | 1 Aug 2026 |
| Final submission | 30 Sep 2026 |
| Award ceremony (ESCAP Bangkok) | 15 Oct 2026 |

## 7. Out of scope / non-goals

- Broad NTM classification (1.3) — only redirect to digital-trade / ICT-goods provisions.
- Document-level summaries (R6).
- Anything that breaks when an adapter is swapped (R12).

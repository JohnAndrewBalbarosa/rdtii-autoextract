# Legal-AI Landscape — Research Brief (2026-06-29)

Research-first pass for the **Legal Expert module** + autonomous-extraction platform vision.
Decisions it serves (all confirmed with the architect):

- **RDTII is the live target**; PH legal sites were illustrative only.
- **Hybrid by criticality:** agent *tags* + *interprets/verifies*; deterministic *assembles
  hierarchy + clusters* (the reproducible core).
- **Phase the model:** deterministic rules + prompted LLM first; **LoRA adapter later** (design
  the seam now, no serving infra yet).
- **Eval:** RDTII F1 + a new hierarchy/citation eval + **LegalBench**.
- **Read-only first**; browser *actions* deferred.
- **Apache-2.0 / self-hostable** is a hard constraint → license is a first-class filter.

> ⚠️ **License filter (drives every "adopt" call):** MIT / BSD / Apache-2.0 = compatible.
> **AGPL** (LexNLP, Skyvern, Firecrawl-as-code, Neo4j-GPL) = avoid or isolate as a separate
> service. **CC-BY-NC / CC-BY-SA** data (Pile of Law, parts of LawInstruct, some legal
> encoders) = NonCommercial/ShareAlike taint — filter before any commercial use.

---

## 1. Legal reasoning model (the "Legal Expert")

| Thing | What | License | Call |
|---|---|---|---|
| **SaulLM / Saul-7B-Instruct** (Equall) | First open legal LLM family (Mistral/Mixtral base, 30B–540B legal tokens + instruct + DPO). 141B reportedly beats GPT-4 on LegalBench-Instruct | **MIT** | **ADOPT** as the reasoning base when we phase to a model (7B for cost; 54B/141B if GPU allows) |
| **LegalBench** | De-facto legal-reasoning benchmark, 162 tasks (issue-spot, rule-recall/application/conclusion, interpretation) | open (per-task varies) | **ADOPT** as external eval; wire the extraction/interpretation subset into the F1 harness |
| **LawInstruct** | Legal instruction dataset (58 sets, 17 jurisdictions); FLawN-T5 ≈ +15 LegalBench, no MMLU loss | mixed (filter!) | **ADOPT recipe + permissive subsets** only |
| **LexLM / Legal-BERT** encoders | RoBERTa/BERT legal encoders — for classification/NER/embeddings (extraction side) | often **CC-BY-SA** | **ADOPT selectively**, prefer MIT/Apache; never for reasoning |
| Community Law-Mistral fine-tunes | jurisdiction-narrow, weak eval, hallucinate | mixed/undocumented | **IGNORE** (use SaulLM instead) |

**Adaptation + serving (the deferred adapter seam):** QLoRA adapters on an Apache/MIT base
(Saul-7B/Mistral-7B), served via **vLLM multi-LoRA** (→ **S-LoRA** at many adapters). All
Apache-2.0. This is exactly the "Base + Legal/Recruitment/… adapter hot-swap" you sketched —
defer the infra, but the LLMProvider port should not preclude it.

## 2. Structure, parsing, chunking, KG (the deterministic core)

| Thing | What | License | Call |
|---|---|---|---|
| **Akoma Ntoso (LegalDocML)** | OASIS XML standard encoding exactly our hierarchy (Code→Book→Title→Chapter→Article/Section) + FRBR Work/Expression (versions/amendments) | open standard | **ADOPT a subset** as the canonical internal structural schema — the target our breadcrumb tree (#2) maps onto |
| **eyecite** (Free Law Project) | citation extraction/normalization | **BSD-2** | **ADOPT** for explicit citation detection |
| **Hierarchy-aware chunking** | chunk per Article/Section + parent path; evidence: structure-aware ≫ fixed-token (nDCG@5 .46 vs .24) | libs MIT/Apache | **ADOPT** — highest-ROI, deterministic, aligns #25/#26 |
| **SAT-Graph RAG / LRMoo Graph RAG** | structure+temporal legal KG with point-in-time retrieval, auditable query policy | papers (no OSS) | **ADAPT** as the KG architecture spine |
| **Legal KG (typed edges)** | nodes=provisions/cases, edges=`cites`/`amends`/`interprets`/`implements` | — | **ADAPT**: build citation+amendment edges deterministically; LLM only for fuzzy relations, HITL-gated |
| Graph backend | Neo4j is **GPL/commercial** | — | prefer **Postgres / Apache AGE / JanusGraph** |
| **LexNLP** | legal NLP toolkit | **AGPL** | **AVOID/ISOLATE** |
| **Blackstone** | UK legal spaCy NER | Apache but **dead** | **ADAPT** patterns only |

**Amendments/cross-refs:** explicit cues ("is amended", "is repealed", "pursuant to Section
12(b)") are reliably **rules-detectable** → deterministic layer resolves them to canonical
AKN-style IDs; route implicit/ambiguous refs to the LLM + HITL.

## 3. Browser agents + strategy reuse (the platform layer, read-only-first)

| Thing | What | Read/Action | License | Call |
|---|---|---|---|---|
| **LaVague** | DOM+retrieval; generates reusable Playwright scripts | action (but emits scripts) | **Apache-2.0** | **ADOPT/ADAPT** — license-perfect, script-emitting fits deterministic-first |
| **browser-use** | DOM element-indexing for the LLM | action | **MIT** | **ADAPT** the DOM-indexing for our read-only extractor |
| **Agent-E** | DOM "distillation" (a11y-tree-like) | action | **MIT** | **ADAPT** distillation |
| **Skyvern / Firecrawl** | mature action/extract | action | **AGPL** | **IGNORE for code reuse**; reference only |
| **a11y-tree extraction** | role/label locators survive cosmetic DOM change | read | research | **ADOPT** as a stable locator surface |
| **Agent Workflow Memory / Synapse / AutoScraper** | reuse workflows/trajectories across similar sites (+24–51% SR); cross-page selector generalization | — | research | **ADOPT concepts** — this IS your "Strategy/Action RAG" |
| **Self-healing scrapers** | on selector failure, LLM proposes new selectors, validate vs live DOM + schema before persist | — | pattern | **ADOPT** — LLM as *healer* behind deterministic selectors (matches "AI behind a validator") |

**Strategy-reuse synthesis (your "Jobstreet ≈ Greenhouse" idea):** a **strategy store keyed by
site/page embedding** (Synapse-style retrieval) holding **deterministic selector sets +
parameterized action/extraction programs** (AWM/AutoScraper), with an **LLM healer** that only
fires on failure and must pass schema validation before the new strategy is saved. This is the
generalization of the existing **scaffold registry**, keeping the hot path deterministic + read-only.

**Eval for the agent layer:** **WebArena**-style programmatic outcome checks (deterministic) +
**Mind2Web** element/operation-F1 (maps onto our F1 harness) + **WebVoyager** GPT-4V judge as a
fallback for open-ended extraction.

## 4. Compliance (read-only-first)

Honor robots.txt; prefer public/unauthenticated pages; no credentialed login/form-submit in the
default path; respect rate limits; cache; per-site allow/deny. **Do not build anti-bot evasion**
(Skyvern itself gates that to cloud — it's the legally sensitive part). Authenticated *actions*
(login/upload/apply) are a separate, deferred, HITL-gated track.

## 5. What maps to existing work / backlog

- Hierarchy chunking + KG ↔ **#2** (sectioning) → **#25** (PDF) → **#26** (DuckDB) → KG layer.
- Legal reasoning model ↔ **#8** (re-scope: legal hierarchy/citation, not just RDTII indicator) + **#9/#28** (LLM seam/extractor) + LoRA seam.
- Strategy RAG ↔ generalize the **scaffold registry** + **VectorStore (#11)**.
- Eval ↔ extend the **F1 harness** with LegalBench + hierarchy/citation metrics.

---

## Sources
See the three source lists captured in the session research (SaulLM 2403.03883; SaulLM-54B/141B
2407.19584; LegalBench 2308.11462; LawInstruct 2404.02127; S-LoRA 2311.03285; Akoma Ntoso OASIS;
eyecite/Free Law Project; SAT-Graph & LRMoo Graph RAG 2505.00039; legal chunking 2603.06976;
WebVoyager 2401.13919; SeeAct 2401.01614; WebArena; Mind2Web; Agent Workflow Memory; AutoScraper
2404.12753; vLLM multi-LoRA docs). Full URLs in the session transcript.

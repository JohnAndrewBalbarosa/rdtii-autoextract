# Zetarix / rdtii-autoextract Mega README

This is the long-form operating guide for the `rdtii-autoextract` repository.
The short GitHub landing page is [README.md](README.md).

## 1. Purpose

Zetarix is an AI-assisted pipeline for extracting and validating public legal
evidence for the UN ESCAP Regional Digital Trade Integration Index (RDTII).

The current implementation focuses on the mandatory competition scope:

- Pillar 6: Cross-border Data Flows
- Pillar 7: Domestic Data Protection

The practical goal is simple: given an economy and pillar, produce structured
rows that a human reviewer can verify quickly against the source law.

## 2. Output Contract

The authoritative output reference is:

```text
docs/OUTPUT_TEMPLATE_31MAY.xlsx
```

The `Output Data` sheet uses the 13-column contract below:

```text
Economy
Law Name
Law Number / Ref
Last Amended
Indicator ID
Article / Section
Discovery Tag
Location Reference
Verbatim Snippet
Mapping Rationale
Source URL
Confidence
Notes
```

The code mirrors this in:

```text
backend/core/pipeline/output_emitter.py
```

`output.csv` is the primary submission artifact. `output.json` is the audit
envelope used to preserve grouped law/provision context for review.

## 3. Training Data

The two ESCAP workbooks are treated as training/evaluation data:

```text
docs/ESCAP-RDTII-2.1_ Round 1 Database.xlsx
docs/ESCAP-RDTII-2.1_ Round 2 Database.xlsx
```

The loader is:

```text
backend/core/pipeline/golden_dataset.py
```

Current parsed coverage:

- 225 gold Pillar 6/7 records
- 477 reference items from seed CSVs
- 10 economies:
  - Australia
  - China
  - India
  - Indonesia
  - Lao PDR
  - Malaysia
  - Mongolia
  - Russian Federation
  - Singapore
  - Thailand
- Pillar split:
  - Pillar 6: 82 records
  - Pillar 7: 143 records

## 4. Why F1 Exists

F1 is used for training and evaluation, not as a replacement for legal review.

The model/pipeline produces predicted rows. The gold workbooks provide known
correct mappings. A predicted row should only count as correct when it matches:

- same economy
- same pillar
- same canonical indicator label
- same law identity by act-name similarity or source URL overlap

Precision answers: "Of the rows the system emitted, how many were correct?"

Recall answers: "Of the known correct rows, how many did the system find?"

F1 balances both. This is suitable for this project because the model must both
retrieve evidence and classify it into the correct RDTII indicator. A system that
emits many extra rows should lose precision. A system that misses many gold rows
should lose recall.

Important limitation: F1 cannot prove legal correctness alone. Final acceptance
still depends on human-verifiable citations, exact snippets, source URLs, and
location references.

## 5. Pipeline Modes

The CLI entry point is:

```text
backend/run.py
```

### 5.1 Gold Mode

Gold mode is offline and deterministic:

```powershell
cd backend
python run.py --country SG --pillar 6 --source gold --out-dir ./out
```

It builds output rows from the reviewer-provided training data. This is useful
for checking the output schema, scoring code, country aliases, and downstream
CSV/JSON generation without relying on network access.

### 5.2 Live Mode

Live mode attempts real retrieval and extraction:

```powershell
cd backend
python run.py --country SG --pillar 6 --source live --out-dir ./out
```

If live crawling yields no findings, the CLI falls back to gold output so the
reviewer contract still produces files. The log records that fallback.

## 6. HTML vs PDF Law Scraping

PDF and HTML law sources have different risks.

### 6.1 PDF

PDF is bounded. If the URL points to a law PDF, the whole file is treated as the
document. The pipeline can extract text and use page/document context as the
location basis.

Relevant modules:

```text
backend/adapters/botting/l4_transport/fetch_result.py
backend/adapters/botting/l4_transport/pdf_parser.py
```

### 6.2 HTML

HTML is not automatically bounded. A page may contain:

- statute text
- navigation
- footer links
- sidebars
- breadcrumbs
- cookie banners
- commentary or related links

The current implementation reduces that risk by:

- applying site-specific scaffolds for known portals
- removing boilerplate elements
- targeting legal content containers
- extracting section-level text with anchors/paths
- using those anchors/paths for `Location Reference`

Relevant modules:

```text
backend/adapters/botting/l6_presentation/dom_cleaner.py
backend/adapters/botting/l6_presentation/html_sections.py
backend/adapters/botting/scaffolds/
```

Known scaffolds:

```text
homeaffairs.gov.au
sso.agc.gov.sg
pdpc.gov.sg
pdp.gov.my
```

## 7. Site Scaffold Role

Scaffolds are the first defense against scraping non-law page chrome.

The registry is:

```text
backend/adapters/botting/scaffolds/scaffold_registry.py
```

Each scaffold can define:

- whether the domain is supported
- URL normalization or fetch URL conversion
- preferred content selectors
- boilerplate selectors to remove

This lets the pipeline treat a Singapore statute page differently from an
Australian government guidance page or a Malaysia PDP portal page.

## 8. Extraction

The deterministic extraction adapter is:

```text
backend/adapters/extraction/mock_provision_extractor.py
```

Despite the name, it is useful for testing because it emits real snippets from
retrieved document text using deterministic rules. It proves that the
fetch-clean-section-output path works without requiring an LLM API key.

Future model-based extraction should implement the same port boundary instead
of changing the output contract.

## 9. Current Algorithm

The current algorithm has two separate jobs:

1. Produce reviewable RDTII output rows.
2. Match/tag legal sections efficiently for training, retrieval, and validation.

It is important not to confuse this with the older concept-graph idea. The old
complete-graph, edge-weight, theta-pruning, community-detection, FCA, and
PageRank plan is superseded. The implemented matching substrate is now a
tags-only `SetTrieIndex`.

### 9.1 End-to-end row-generation algorithm

For a normal `run.py` execution, the pipeline is:

```text
country + pillar
  -> resolve country alias
  -> load gold/reference data
  -> choose source mode
  -> retrieve or synthesize candidate law documents
  -> reduce each source to plain legal text
  -> extract candidate provisions
  -> tag rows as KNOWN or NEW
  -> emit output.csv and output.json
```

The two source modes differ only in where candidate rows come from:

- `--source gold`: build rows directly from the ESCAP Round 1/2 training
  workbooks. This is deterministic and offline.
- `--source live`: crawl seed URLs, clean PDF/HTML content, run the extractor,
  then fall back to gold rows if no live findings are produced.

### 9.2 Retrieval and document-boundary algorithm

For each seed URL:

```text
URL
  -> scaffold lookup by domain
  -> optional scaffold fetch-url normalization
  -> HTTP fetch
  -> if PDF: parse full PDF text
  -> if HTML: strip boilerplate, select legal content, extract sections
  -> CrawledDocument(url, economy, text, is_pdf, sections)
```

PDF is treated as bounded because the file is the law document. HTML is treated
as unbounded until cleaned, because the page may contain navigation, footers,
related links, commentary, and cookie banners. For HTML, the algorithm prefers
section anchors and breadcrumb-like paths so `Location Reference` can point to
the specific legal section rather than the whole page.

Relevant code:

```text
backend/run.py
backend/adapters/botting/l4_transport/http_client.py
backend/adapters/botting/l4_transport/pdf_parser.py
backend/adapters/botting/l6_presentation/dom_cleaner.py
backend/adapters/botting/l6_presentation/html_sections.py
backend/adapters/botting/scaffolds/
```

### 9.3 Deterministic provision extraction algorithm

The current deterministic extractor scans the cleaned document text and section
metadata for indicator-relevant provision patterns. It emits `Finding` rows with:

- law name
- article/section
- source URL
- location reference
- verbatim snippet
- confidence
- indicator

For HTML, it maps matched text back to the containing `HtmlSection` when
possible. That is how a row gets a section anchor or path in `Location Reference`
instead of only a bare URL.

Relevant code:

```text
backend/adapters/extraction/mock_provision_extractor.py
backend/core/domain/document.py
backend/core/domain/entities.py
```

### 9.4 Guided tagging algorithm

The guided-tagging flow is for turning parsed law sections into tagged
`ConceptNode` objects.

```text
ParsedDocument
  -> high-context DocumentGuide for the whole law
  -> one bounded SectionTaggingTask per section
  -> low-context tagger proposes tags + evidence quote
  -> reconciler validates confidence, taxonomy, and quote support
  -> accepted ConceptNode objects or review items
```

The key rule is evidence support: a tag is accepted only when its evidence quote
appears in the source section text. The guide can narrow labels and provide
context, but it is not accepted as evidence by itself.

Relevant code:

```text
backend/core/pipeline/guided_tagging.py
backend/core/domain/concept_node.py
backend/core/domain/document.py
```

### 9.5 Structural fallback algorithm

The structural extractor is deterministic and model-free. It walks ordered
heading blocks with a heading stack:

```text
heading levels
  -> maintain breadcrumb stack
  -> slug breadcrumb headings
  -> combine blocks with the same breadcrumb scope
  -> emit ConceptNode(section_id, text, caption, tags)
```

Example:

```text
Privacy Law > Cross-Border Data Flows
  -> section_id: privacy-law/cross-border-data-flows
  -> tags: privacy-law, cross-border-data-flows
```

Relevant code:

```text
backend/adapters/extraction/structural_extractor.py
```

### 9.6 Set-trie matching algorithm

`SetTrieIndex` is the current fast matching substrate. It replaces the older
similarity graph.

Each stored item is:

```text
node_id + frozenset(tags)
```

Build step:

```text
items
  -> count tag frequencies
  -> global tag order: rarest first, string tie-break
  -> sort each item's tags by that global order
  -> insert each sorted tag set as a trie path
```

Why rarest-first matters: a rare tag placed high in the trie gates a large
subtree. If a query does not contain that rare tag, the algorithm skips the
whole branch immediately.

Subset query:

```text
query_subsets(Q)
  -> return stored items whose tags are all present in Q
  -> descend only into child tag t when t is in Q
  -> prune any branch whose required tag is absent
```

Superset query:

```text
query_supersets(Q)
  -> return stored items that contain every tag in Q
  -> walk paths in global tag order
  -> consume required tags when found
  -> prune once ordering proves a needed tag cannot appear deeper
```

Properties:

- acyclic by construction, because each path is strictly ordered
- deterministic, because tag ordering and outputs are sorted
- explainable, because matching is set inclusion rather than opaque similarity
- fast for this use case, because irrelevant branches are pruned early

Relevant code:

```text
backend/core/pipeline/set_trie.py
backend/core/pipeline/parallel_matcher.py
backend/tests/test_set_trie.py
```

### 9.7 Scoring and training algorithm

Scoring evaluates predicted `Finding` rows against gold records from the two
training workbooks.

The match rule is:

```text
same pillar
AND same canonical indicator
AND same country when both sides specify one
AND (shared normalized URL OR act-name Jaccard similarity >= threshold)
```

Then the scorer performs greedy one-to-one matching and computes:

```text
precision = true_positives / (true_positives + false_positives)
recall    = true_positives / (true_positives + false_negatives)
F1        = harmonic mean of precision and recall
```

The indicator requirement is deliberate. A model should not score as correct
just because it found the right law if it assigned the wrong RDTII indicator.

Relevant code:

```text
backend/core/pipeline/scoring.py
backend/core/pipeline/golden_dataset.py
backend/tests/test_scoring.py
backend/tests/test_golden_dataset.py
```

### 9.8 What the algorithm is not

The current implementation is not:

- a legal reasoning engine
- a final authority on whether a website paragraph is part of a law
- a graph PageRank/FCA hierarchy system
- an LLM-only extraction flow
- a replacement for human review

The intended model is: deterministic boundaries and scoring first, model-based
extraction second, human-verifiable legal evidence always.

## 10. Architecture

The backend follows a ports-and-adapters style:

```text
backend/core/       # domain, ports, pipeline logic
backend/adapters/   # concrete scraping, extraction, LLM, transport implementations
backend/app/        # FastAPI reference adapter
backend/run.py      # CLI reviewer contract
```

The core should not depend on browser, HTTP, FastAPI, or LLM implementation
details. Concrete tools belong in adapters.

More detail:

```text
backend/docs/ARCHITECTURE.md
backend/docs/SCRAPING_STRATEGY.md
backend/docs/SCORING_STRATEGY.md
backend/docs/ROUND1_SUBMISSION_SPEC.md
```

## 11. Setup

Recommended Windows PowerShell setup:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

For Linux/macOS:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 12. Common Commands

Run one offline gold export:

```powershell
cd backend
python run.py --country SG --pillar 6 --source gold --out-dir ./out
```

Run live with fallback:

```powershell
cd backend
python run.py --country SG --pillar 6 --source live --out-dir ./out
```

Limit output rows:

```powershell
cd backend
python run.py --country SG --pillar 6 --source gold --limit 5 --out-dir ./out
```

Run tests:

```powershell
cd backend
python -m pytest -q
```

Run validation harness:

```powershell
cd backend
python run_validation.py
```

## 13. Output Files

The CLI writes:

```text
out/output.csv
out/output.json
out/logs/run.log
```

`output.csv` is the spreadsheet-facing deliverable. It must preserve exact
header names and order.

`output.json` groups findings by law and preserves provision-level audit fields.

`run.log` records country, pillar, source, fallback behavior, row counts, and
extraction events.

## 14. Country Aliases

The CLI accepts aliases for the current training-data economies:

```text
AU  Australia
SG  Singapore
MY  Malaysia
CN  China
IN  India
ID  Indonesia
LA  Lao PDR / Laos
MN  Mongolia
RU  Russian Federation / Russia
TH  Thailand
```

## 15. Discovery Tags

`Discovery Tag` is either:

- `KNOWN`: row matches gold/reference data
- `NEW`: row is not found in the known evidence baseline

The logic is in:

```text
backend/run.py
backend/core/pipeline/scoring.py
```

New evidence should be treated as candidate evidence until a reviewer verifies
the source and mapping.

## 16. Scoring Rules

Scoring code lives in:

```text
backend/core/pipeline/scoring.py
```

The match rule requires:

- same pillar
- same canonical indicator
- same country when both sides specify country
- either source URL overlap or act-name similarity above threshold

This avoids a false success where the system finds the right law but assigns the
wrong RDTII indicator.

## 17. Testing Strategy

Important test files:

```text
backend/tests/test_golden_dataset.py
backend/tests/test_output_emitter.py
backend/tests/test_scoring.py
backend/tests/test_dom_sections.py
backend/tests/test_html_sections.py
backend/tests/test_mock_provision_extractor.py
backend/tests/test_run_cli.py
backend/tests/test_pdf_pipeline.py
backend/tests/test_scaffold_registry.py
```

Before publishing code changes, run:

```powershell
cd backend
python -m pytest -q
```

Recent known-good result:

```text
303 passed
```

## 18. Compliance and Access Boundaries

This repository is intended for public legal sources. Retrieval logic should
stay within compliance-oriented boundaries:

- public laws and government sources only
- no credential bypass
- no private/non-public data
- bounded retry/backoff
- rate-awareness and audit logs
- human review for final legal claims

See:

```text
docs/COMPLIANT_AUTOMATION_GUIDE.md
backend/docs/SCRAPING_STRATEGY.md
```

## 19. Known Gaps

- Live extraction still needs careful per-portal validation before being trusted
  as a final legal-data source.
- HTML pages can include non-law content; scaffolds and section anchors reduce
  risk but do not remove the need for review.
- F1 is a training/evaluation metric, not a legal correctness guarantee.
- The deterministic extractor and set-trie matcher are not substitutes for a
  fully trained model; they are reliable wiring and regression-test components.
- OCR quality must be measured separately for scanned PDFs.

## 20. Development Rules of Thumb

- Keep output headers exactly aligned with `OUTPUT_TEMPLATE_31MAY.xlsx`.
- Treat `Verbatim Snippet` as exact source text, not paraphrase.
- Prefer section anchors/paths for HTML `Location Reference`.
- Prefer page/document references for PDF `Location Reference`.
- Do not let scraping code leak into core domain logic.
- Add tests when changing scoring, output columns, country aliases, or scraping
  boundaries.
- Keep `MEGA_README.md` aligned with `set_trie.py`; do not describe the old
  graph/PageRank/FCA plan as the current algorithm.

## 21. License

Apache License 2.0. See:

```text
LICENSE
backend/LICENSE
```

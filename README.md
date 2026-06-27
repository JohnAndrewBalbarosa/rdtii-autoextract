# Zetarix / rdtii-autoextract

AI-assisted extraction and validation pipeline for the UN ESCAP Regional Digital
Trade Integration Index (RDTII), focused on:

- Pillar 6: Cross-border Data Flows
- Pillar 7: Domestic Data Protection

The project turns public law sources into citation-backed rows that match the
Round 1 output template. It supports offline training-data runs, live PDF/HTML
scraping, exact output headers, and repeatable scoring against the ESCAP Round 1
and Round 2 training datasets.

## What Works Now

- Loads both training workbooks:
  - `docs/ESCAP-RDTII-2.1_ Round 1 Database.xlsx`
  - `docs/ESCAP-RDTII-2.1_ Round 2 Database.xlsx`
- Parses 225 Pillar 6/7 gold records across 10 economies.
- Emits the exact `docs/OUTPUT_TEMPLATE_31MAY.xlsx` column contract:
  `Economy`, `Law Name`, `Law Number / Ref`, `Last Amended`,
  `Indicator ID`, `Article / Section`, `Discovery Tag`,
  `Location Reference`, `Verbatim Snippet`, `Mapping Rationale`,
  `Source URL`, `Confidence`, `Notes`.
- Handles PDF and HTML sources:
  - PDF: extracts text from the bounded law document.
  - HTML: strips boilerplate and maps text to section anchors/paths when
    available.
- Hardens site scaffolds for the current AU/SG/MY scoring scope, including:
  - `sso.agc.gov.sg`
  - `pdpc.gov.sg`
  - `homeaffairs.gov.au`
  - `pdp.gov.my`
- Scores predictions with precision/recall/F1 against gold data, requiring the
  correct country, pillar, indicator, and law/source identity.

For the full operating guide, see [MEGA_README.md](MEGA_README.md).

## Quick Start

From the backend directory:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Run the offline gold pipeline:

```powershell
python run.py --country SG --pillar 6 --source gold --out-dir ./out
```

Run the live scraper path with offline fallback:

```powershell
python run.py --country SG --pillar 6 --source live --out-dir ./out
```

Outputs are written to `--out-dir`:

- `output.csv`: primary submission table using the official 13-column template.
- `output.json`: grouped law/provision audit payload.
- `logs/run.log`: crawl/extraction/run trace.

## Supported Country Aliases

The CLI accepts common aliases for all countries present in the Round 1 and
Round 2 training data:

`AU`, `SG`, `MY`, `CN`, `IN`, `ID`, `LA`, `MN`, `RU`, `TH`

It also accepts full names such as `Australia`, `Singapore`, `Malaysia`,
`China`, `India`, `Indonesia`, `Lao PDR`, `Mongolia`,
`Russian Federation`, and `Thailand`.

## Repository Layout

```text
.
|-- backend/
|   |-- run.py                         # CLI entry point
|   |-- app/                           # FastAPI reference adapter
|   |-- core/                          # Domain, ports, pipeline, scoring
|   |-- adapters/                      # Scraping, extraction, LLM adapters
|   |-- tests/                         # Backend test suite
|   `-- docs/                          # Architecture and strategy docs
|-- docs/                              # Training data, output template, proposal docs
|-- frontend/                          # Reviewer/audit UI shell
`-- README.md
```

## Documentation Map

- **[docs/departments/](docs/departments/README.md)** — the delegation handbook: the
  codebase split into 4 owner-aligned departments, each with a README (modularity view)
  and a PlantUML component diagram. Start here for task delegation / reverse-prompting.
- **Per-folder READMEs** — most code folders carry a `README.md` with a Mermaid diagram of
  what happens inside that module (e.g. [`backend/core/`](backend/core/README.md),
  [`backend/adapters/botting/`](backend/adapters/botting/README.md),
  [`frontend/src/`](frontend/src/README.md)).
- **[backend/docs/](backend/docs/)** — architecture & strategy (ARCHITECTURE, GRAPH_PIPELINE,
  SCORING_STRATEGY, SCRAPING_STRATEGY).
- **[MEGA_README.md](MEGA_README.md)** — long-form operating guide.

## Key Backend Modules

- `backend/run.py`: country/pillar CLI, gold/live source selection, output writing.
- `backend/core/pipeline/golden_dataset.py`: training workbook and reference CSV loader.
- `backend/core/pipeline/output_emitter.py`: CSV/JSON output contract.
- `backend/core/pipeline/scoring.py`: precision/recall/F1 and discovery diff.
- `backend/adapters/botting/l6_presentation/dom_cleaner.py`: HTML cleaning and section extraction.
- `backend/adapters/botting/l6_presentation/html_sections.py`: HTML section helpers.
- `backend/adapters/botting/scaffolds/`: per-site law portal handling.
- `backend/adapters/extraction/mock_provision_extractor.py`: deterministic extraction adapter.

## Verification

Run the backend suite:

```powershell
cd backend
python -m pytest -q
```

At the time this README was updated, the full backend suite passed:

```text
303 passed
```

## Notes on F1 Scoring

F1 is suitable here as an internal training/evaluation metric because the task is
row retrieval and classification: the model must find the right legal evidence
and map it to the right RDTII indicator. Precision catches hallucinated or wrong
rows; recall catches missed gold rows; F1 balances the two.

F1 is not the final product by itself. The final deliverable is still a
human-reviewable submission table with exact citations, verbatim snippets, source
URLs, and location references.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [backend/LICENSE](backend/LICENSE).

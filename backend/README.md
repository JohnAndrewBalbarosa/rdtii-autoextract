# RDTII Engine — Backend

Framework-agnostic core + FastAPI reference adapter by **Team Arkova** for the **Global
Hackathon on AI for Digital Trade Regulatory Analysis** (UN ESCAP & KMITL, 2026). Apache 2.0.

Automates ~80% of the RDTII workflow — **discover → retrieve → OCR → chunk → extract →
map → review** — for **Pillar 6 (Cross-border Data Flows)** and **Pillar 7 (Domestic Data
Protection)**, emitting article-level findings with the 6 mandatory fields.

> Frontend (reviewer / audit UI) lives in a **separate repo**: `rdtii-frontend`.

## Quick Start

**Zetarix** — automated RDTII evidence extraction: hand it a country + pillar, get back
audited, citation-backed findings as CSV + JSON, with no manual steps.

### Setup

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
playwright install chromium                         # only needed for live crawling
```

### Run (one command — the reviewer contract)

```bash
python run.py --country SG --pillar 6
```

Accepts aliases / misspell-tolerant codes (`SG`/`Singapore`, `AU`/`Australia`,
`MY`/`Malaysia`, case-insensitive) and `--pillar 6` or `7`. Useful flags:
`--out-dir ./out` · `--source live|gold` · `--limit N`.

### Outputs (written to `--out-dir`, default `./out`)

| File | What |
| ---- | ---- |
| `output.csv` | Primary submission table — the exact p.14 columns (`Economy … Notes`), one row per provision, verbatim snippet + Discovery Tag (`NEW`/`KNOWN`) in every row. |
| `output.json` | Supplementary envelope — findings grouped by law with `provisions[]`, `source_pdf_path`, `ocr_quality_cer`, `processing_time`, `model_version`, and `raw_context` per provision. |
| `logs/run.log` | Run trace (country, pillar, source, row/NEW/KNOWN counts). |

### Pinned versions (no "latest")

Runtime libs are version-floored in [`requirements.txt`](requirements.txt): `playwright>=1.45`
(crawl), `pypdf>=4.0` (PDF text), `beautifulsoup4>=4.12` (HTML), `networkx>=3.2` +
`python-louvain>=0.16` + `concepts>=0.9` (concept graph). For a reproducible submission
build, pin exact versions with `pip freeze > requirements.lock`. The LLM/OCR tools are
selected by config, not hardcoded — pin the chosen model + OCR engine in that config (no
floating `latest` tags).

### Open-source fallback

The LLM layer is a **model-agnostic router** ([`adapters/llm/router.py`](adapters/llm/router.py)):
swap a commercial API for an open-weight model (e.g. Llama 3) by config, no core rewrite
(R12). When **no API key** is configured, `--source live` prints a clear notice and falls
back to `--source gold` — a fully **offline** mode that builds findings from the
reviewer-validated golden dataset, so `output.csv` / `output.json` are always produced
with no network and no LLM.

## Layout

```
core/        # AGNOSTIC domain — ports (interfaces), entities, pipeline use-cases. No framework imports.
adapters/    # Concrete LLM / OCR / vector / crawler implementations. Swap a tool here.
app/         # FastAPI reference adapter (SWAPPABLE) — thin HTTP layer, no domain logic.
docs/        # ARCHITECTURE, REQUIREMENTS (Q&A-traced), TECHNICAL_MEMO.
```

Why ports & adapters: swappability is heavily scored (R12, 40 pts). The core depends only
on interfaces; concrete tools (incl. open-weight Llama 3) are swapped via config. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run (dev)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
uvicorn app.main:app --reload    # http://127.0.0.1:8000/health
```

## License

[Apache 2.0](LICENSE).

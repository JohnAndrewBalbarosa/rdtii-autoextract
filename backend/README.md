# RDTII Engine — Backend

Framework-agnostic core + FastAPI reference adapter for the **Global Hackathon on AI for
Digital Trade Regulatory Analysis** (UN ESCAP & KMITL, 2026). Apache 2.0.

Automates ~80% of the RDTII workflow — **discover → retrieve → OCR → chunk → extract →
map → review** — for **Pillar 6 (Cross-border Data Flows)** and **Pillar 7 (Domestic Data
Protection)**, emitting article-level findings with the 6 mandatory fields.

> Frontend (reviewer / audit UI) lives in a **separate repo**: `rdtii-frontend`.

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

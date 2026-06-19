# Scraping & Compliant-Access Strategy

> How Zetarix retrieves public law documents (HTML + PDF) from government portals,
> including anti-bot handling and IP rotation. Handling messy/anti-bot/scanned portals
> is an explicit, sanctioned requirement (Q&A 5.4 → R19). Rotation distributes load and
> avoids IP bans during legitimate bulk retrieval of **public** legislation — it is not
> for authentication evasion or non-public data.

## Layered, model-agnostic architecture (conceptual cohesion)

Scraping is **fully decoupled from any LLM** — fetch/clean/PDF need zero model. Only
tagging/validation touch `LLMProvider` (already a port, see `adapters/llm/router.py`).
So the whole retrieval path runs with no model configured at all.

| Layer | "What it owns" | Key pieces |
| ----- | -------------- | ---------- |
| **L4 Transport** — *how bytes arrive* | fetch strategy, proxies/rotation, typed result, PDF download | `http_client.py`, `playwright_client.py`, `factory.py` (`TransportFactory`), `pdf_parser.py`, `fetch_result.py`, `proxy_provider.py`, `proxy_providers.py` |
| **L6 Presentation** — *bytes → clean text* | DOM cleaning, PDF text extraction | `dom_cleaner.py`, `PdfParser.extract_text` |
| **L7 Application** — *clean text → Findings* | orchestration, site scaffolds, validation | `pipeline_adapter.py`, `scaffolds/`, `scraper_orchestrator.py`, `document_validator.py` |

Top entry point: `ScraperOrchestrator.scrape_and_validate(urls)`.

## Typed transport result (fixes the binary/PDF crash)

`FetchResult(url, status, content_type, body: bytes)` with a `.text` property that decodes
**only** text content types (charset-aware, `errors='replace'`) and an `.is_pdf` helper.
`HttpClient.fetch_raw() -> FetchResult` never decodes binary, so PDFs no longer crash the
pipeline. `PipelineAdapter.scrape_url()` routes `is_pdf` → `PdfParser`, HTML → `DomCleaner`.
**Proven:** a real Malaysian law PDF extracted to 14,726 chars of text.

## Bypassing: IP rotation + header realism (config-driven, provider-agnostic)

A `ProxyProvider` port (`get()`, `report(endpoint, ok)`, `rotate()`) with swappable adapters
— **no hardcoded vendor**:

| `PROXY_MODE` | Adapter | Use |
| ------------ | ------- | --- |
| `none` (default) | `NoProxyProvider` | direct connection |
| `free` | `FreeProxyProvider` | wraps `FreeProxyManager` (free public pool; unreliable) |
| `configured` | `ConfiguredRotatingProxyProvider` | **BYO** paid rotating-residential |
| `simulated` | `SimulatedProxyProvider` | local server for deterministic tests |

BYO credentials via `PROXY_LIST` (comma-separated `scheme://user:pass@host:port`) or
`PROXY_TEMPLATE` (`{session}` placeholder for sticky/rotating sessions). Tunables:
`PROXY_SEED` (deterministic rotation), `PROXY_COOLDOWN`, `PROXY_SIM_HOST/PORT`.

**Ban handling:** on HTTP 403/429 → `report(ok=False)` (cooldown that endpoint) → `rotate()`
→ exponential backoff (injectable sleep) → retry within a bounded budget. A per-domain
throttle enforces a minimum gap between hits to the same host.

**Header realism:** realistic browser UA + `Accept` / `Accept-Language` / `Accept-Encoding`
/ `DNT` / `Upgrade-Insecure-Requests`. **Proven:** `sso.agc.gov.sg`, previously 403 on a bare
request, now returns HTTP 200.

## Site scaffolds

`ScaffoldRegistry` matches a URL's domain to a site-specific scaffold (selectors / access
rules). Present: `homeaffairs.gov.au`, `sso.agc.gov.sg`, `pdpc.gov.sg`. Singapore selectors
are **provisional** — to be refined against live DOM.

## Status (tested, no fabricated claims)

- PDF fetch + extraction: **working** (real extraction confirmed). 17 transport/PDF tests.
- Proxy rotation + ban handling + header realism: **working**, config-driven BYO. 21 tests.
- 403 anti-bot: **resolved** via header realism (live 200 on sso.agc.gov.sg).
- Full backend suite: **114 passed / 0 failed**.

## Gaps / next

- Singapore scaffold selectors are provisional (refine on live DOM).
- `TransportFactory` headless-required heuristic is light; some SPA portals may over-use Playwright.
- No end-to-end test of LLM extraction from a fetched PDF yet (needs a live `LLMProvider`).
- For a real batch crawl across many URLs, add a background **monitor** (progress + ban-rate)
  — deliberately skipped for the small smoke test.

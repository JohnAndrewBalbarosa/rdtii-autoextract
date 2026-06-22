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
`PROXY_TEMPLATE` (`{session}` placeholder for rotating-residential gateways). Tunables:
`PROXY_SEED` (deterministic order), `PROXY_COOLDOWN`, `PROXY_ROTATION`
(`per_request` default | `per_n:<k>` | `sticky`), `PROXY_MAX_RPS_PER_IP` (default 5),
`PROXY_RATE_WINDOW` (default 60s), `PROXY_SIM_HOST/PORT`.

**Rotation is PROACTIVE — "many users, not one spammer":** the egress rotates on *every*
request. Selection is **least-recently-used** with a **per-IP rate budget** — an IP nearing
`PROXY_MAX_RPS_PER_IP` within `PROXY_RATE_WINDOW` is skipped and cooled *before* any server
pushes back, so each IP carries only a low, human-looking request rate. For
rotating-residential gateways a **fresh `{session}` token is minted per request**, so each
request exits from a new IP. We do NOT hammer one IP until it is banned and only then rotate.
Verified: 8 requests over a 4-IP pool spread 2/2/2/2 with no consecutive repeats; template
mode yields a unique exit identity per request.

**Ban handling is only a safety net:** if a 403/429 still occurs it cools that IP, rotates,
and retries with bounded exponential backoff — but because load is distributed up front, a
ban should rarely be reached. This is **best-effort on a sufficiently large pool, not a
guarantee**: a tiny pool under high volume can still exceed a site's tolerance. A per-domain
throttle enforces a minimum gap between hits to the same host.

**Parallel-crawl coordination (the middleman):** when many crawlers run in parallel
(threads/async in one process), independent rotation can make two workers grab the same IP at
once — a site then sees repeated hits from one IP. A central `ProxyPoolBroker` is the single
source of truth for a fixed/finite pool: each IP has a stable index via a hash map
(`_index_of`, O(1) — not a linear/radix scan), an `in_use` flag (so no two workers hold the
same IP simultaneously), and a per-worker usage bitmap (so one worker won't reuse an IP until
it has cycled the pool). `acquire(worker_id)` leases the longest-idle free IP, blocking up to a
timeout when the pool is momentarily occupied; `release()` frees it; a `lease()` context manager
makes `with broker.lease() as ep:` safe. When the pool is momentarily exhausted, waiters join a
**FIFO queue** and a released IP is **handed directly** to the first queued worker that has not
already used it (a worker that already used the freed IP is skipped, never handed a duplicate);
`reset(worker_id)` — and auto-reset once a worker has cycled the whole pool — starts its rotation
fresh. `BrokeredProxyProvider`
(`PROXY_MODE=brokered` / `PROXY_COORDINATED=1`) lets per-thread `HttpClient`s share coordinated
IPs. Verified by a stress probe: 8 threads × 100 leases over a 4-IP pool → **max 1 concurrent
holder per IP, 0 collisions**. (Rotating-residential TEMPLATE mode is already collision-free via
per-request `{session}`, so the broker targets fixed/finite lists.)

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

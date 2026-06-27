# Department 01 — Scraper / Botting

**Mission:** Turn a government-portal URL into clean, structured, machine-readable
sections — reliably, politely, and across messy SPA and PDF sources.

**Agent:** `zx-scraper` · **Discipline:** TDD-first · **Core rule:** implements the
fetch ports, never imports core domain logic beyond document entities.

---

## File structure (what this department owns)

```text
backend/adapters/botting/
├── l4_transport/                 # OSI L4 — physical fetch (HTTP + browser + proxies)
│   ├── factory.py                # TransportFactory: static→dynamic engine selector
│   ├── http_client.py            # HttpClient: realistic headers, throttle, proxy
│   ├── playwright_client.py      # PlaywrightClient: headless JS render + expand-all
│   ├── fetch_result.py           # FetchResult: immutable bytes-safe response (PDF-safe)
│   ├── pdf_parser.py             # PdfParser: download + extract text (pypdf)
│   ├── scroll_settle.py          # settle_page / is_settled: lazy-load settling
│   ├── advanced_crawler.py       # AdvancedCrawler: static/dynamic + script scanning
│   ├── proxy_provider.py         # ProxyProvider protocol + ProxyEndpoint
│   ├── proxy_providers.py        # None/Free/Configured/Brokered/Simulated providers
│   ├── proxy_pool_broker.py      # ProxyPoolBroker: thread-safe fixed-IP pool
│   ├── proxy_config.py           # ProxyConfig / FreeProxyManager
│   ├── simulated_proxy_server.py # ThreadedProxyServer: residential-IP simulator (test)
│   └── demo_crawler.py           # MockWebServer + demo harness (test)
├── l6_presentation/              # OSI L6 — HTML → cleaned sections
│   ├── dom_cleaner.py            # DomCleaner: strip chrome, extract sections, links
│   └── html_sections.py          # join_section_text / section_for_offset / format_location_ref
├── l7_application/               # OSI L7 — task orchestration
│   └── pipeline_adapter.py       # PipelineAdapter: fetch → clean → LLM structure
└── scaffolds/                    # Site-specific portal rules
    ├── base_scaffold.py          # BaseScaffold ABC (selectors, transport, keywords)
    ├── scaffold_registry.py      # ScaffoldRegistry: domain → scaffold lookup
    ├── sso_agc_gov_sg.py         # Singapore Statutes Online (PDF-view rewrite)
    ├── pdpc_gov_sg.py            # Singapore PDPC
    ├── pdp_gov_my.py             # Malaysia PDP
    ├── homeaffairs_gov_au.py     # Australia Home Affairs
    └── legislation_gov_au.py     # Australia Federal Register (Angular SPA → dynamic)
```

---

## Modularity (functional breakdown)

The department is a **three-layer stack plus a plug-in registry**. Each layer is a
separate functional module; you can work on one without understanding the others.

### Module A — Transport (L4): "get the bytes"
Fetches raw content politely and survives messy portals.
- **`TransportFactory`** is the single entry: tries static `HttpClient` first, falls back
  to `PlaywrightClient` when the page is JS-heavy / SPA (detected heuristically).
- **`HttpClient`** sends realistic headers, per-domain throttle, rotating proxies, and
  handles bans/gzip/brotli. Implements the `HtmlFetcherPort`.
- **`PlaywrightClient`** renders JS, clicks expand-all toggles, and uses
  **`scroll_settle.settle_page`** to wait for lazy-rendered content to plateau (this is
  the fix for SPA portals that render on scroll).
- **`PdfParser`** handles the PDF branch; **`FetchResult`** is the bytes-first wrapper so
  PDFs never crash the text path.
- **Proxy subsystem** (`proxy_provider`, `proxy_providers`, `proxy_pool_broker`,
  `proxy_config`) lets the team pick a strategy — none / free-list / configured /
  brokered fixed-pool / simulated residential — without touching call sites.

### Module B — Presentation (L6): "clean the HTML"
Turns raw HTML into ordered, anchored sections.
- **`DomCleaner.extract_sections`** strips boilerplate (nav/footer/script/search/banner +
  scaffold-specified chrome), groups blocks under headings, and attaches **anchors +
  breadcrumb paths** so every section is citable.
- **`DomCleaner.discover_links`** finds PDF + article links for crawl expansion.
- **`html_sections`** are pure helpers: flatten sections to text, map a text offset back
  to its section, and **`format_location_ref`** for the output's Location Reference field.

### Module C — Application (L7): "orchestrate one scrape"
- **`PipelineAdapter.scrape_url`** runs the full flow: scaffold lookup → L4 fetch → L6
  clean → optional LLM markdown/JSON structuring → returns a `ParsedDocument`. Implements
  the `DocumentExtractorPort`. The LLM is injected via `LLMProvider` (Department 02/03
  seam) — it is the only AI surface here and is fully optional.

### Module D — Scaffolds: "site-specific rules without core changes"
- **`ScaffoldRegistry`** matches a URL's domain (substring) to a **`BaseScaffold`**.
- A scaffold declares: custom selectors, boilerplate selectors, relevance keywords,
  forced transport type (e.g. `legislation.gov.au` → dynamic), and URL rewrites
  (e.g. `sso.agc.gov.sg` → PDF view). **Adding a new portal = one new subclass + one
  registry line.** No changes to L4/L6/L7.

---

## Runtime flow (component view)

```
URL ─▶ ScaffoldRegistry.get_scaffold_for_url
     └▶ TransportFactory.fetch_raw ── static (HttpClient) ──▶ FetchResult
                                   └─ JS/SPA → PlaywrightClient + settle_page
        FetchResult.is_pdf ? ─▶ PdfParser.extract_text ─▶ text
                              └▶ DomCleaner.extract_sections ─▶ [HtmlSection]
        (optional) PipelineAdapter LLM structure ─▶ ParsedDocument(sections, tags, links)
```

See [`component.puml`](component.puml) for the full diagram.

---

## Port seams (the contract with the rest of the system)

| Port (defined in Dept 03) | This department's relationship |
|---|---|
| `HtmlFetcherPort` | **Implemented** by `HttpClient`, `PlaywrightClient`, `TransportFactory` |
| `DocumentExtractorPort` | **Implemented** by `PipelineAdapter` |
| `LLMProvider` | **Consumed** (injected) by `PipelineAdapter` — provided by Dept 02/03 |
| `ParsedDocument`, `HtmlSection` (domain) | **Produced** — the handoff to Dept 02 |

> The scraper never imports extraction, scoring, or clustering. It hands off a
> `ParsedDocument` and stops. That boundary is what lets it be tested in isolation.

---

## Verify

```powershell
cd backend
python -m pytest -q tests/test_advanced_crawler.py tests/test_transport_dynamic.py `
  tests/test_dom_sections.py tests/test_html_sections.py tests/test_scroll_settle.py `
  tests/test_scaffold_registry.py tests/test_legislation_scaffold.py `
  tests/test_homeaffairs_scraper.py tests/test_proxy_rotation.py tests/test_web_scraper.py
```

Live debugging: `python tools/inspector_walkthrough.py` (the `--walkthrough` live DOM
debugger for lazy-load portals).

---

## Reverse-prompting hooks (task seeds for delegation)

Hand these to a developer / agent. Scope is pre-bounded so the hexagonal seam stays intact.

1. **New portal support** — *"Add a scaffold for `<domain>` under
   `backend/adapters/botting/scaffolds/`. Subclass `BaseScaffold`, register it in
   `ScaffoldRegistry`, declare selectors/keywords/transport/URL-rewrite. Add a test like
   `tests/test_legislation_scaffold.py`. Do not touch L4/L6/L7 or any core port."*
2. **Harden lazy-load** — *"A portal under-renders sections. Within `l4_transport`, extend
   `scroll_settle`/`PlaywrightClient` settle logic. Prove it with a deterministic test;
   no changes outside `l4_transport`."*
3. **Proxy strategy** — *"Implement a new `ProxyProvider` in `proxy_providers.py` for
   `<provider>`. It must satisfy the `ProxyProvider` protocol and pass
   `tests/test_proxy_provider.py`. No call-site edits."*
4. **Cleaner precision** — *"Sections collapse to one block on `<site>`. Within
   `dom_cleaner.py`, fix grouping. Add a fixture-based test in `tests/test_dom_sections.py`.
   Keep `HtmlSection` shape unchanged (Dept 02 depends on it)."*
   _(See the known sectioning-collapse issue in project memory.)_

**Boundary reminder for every task:** you may edit only files under
`backend/adapters/botting/`. You may **read** `backend/core/ports/` and
`backend/core/domain/document.py` but must not change them.

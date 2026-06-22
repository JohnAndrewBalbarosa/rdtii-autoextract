# HTML Section-Anchor & Scaffold-Hardening Plan (resumable handoff)

> **Status: NOT STARTED.** A background Sonnet worker was dispatched to implement this
> but **stopped (user-requested) before writing any files** — it was still in the
> research / baseline-pytest phase. No code was changed. This doc captures the full
> design so the work can be resumed cold.
>
> Baseline before starting: `cd backend && python -m pytest -q` → **114 passed**. Do not regress.

## Why

PDF sources are bounded — the whole file *is* the law, page number = Location Reference.
HTML sources are not: a page mixes legal text with chrome (nav/header/footer/sidebar/
related-links/cookie banners). We must (1) extract **only** the legal-content container
on known gov portals, and (2) capture each provision's section **anchor/path** to emit as
the template `Location Reference` (`#s26` or `Part IV > Section 26`) and feed verbatim
snippets to the output emitter. Source of truth for the output contract:
`docs/ROUND1_SUBMISSION_SPEC.md` + `docs/OUTPUT_TEMPLATE_31MAY.xlsx`.

## Feature 1 — anchor-aware HTML section extraction

1. **`core/domain/document.py`** — add frozen dataclass `HtmlSection(heading: str, text: str,
   anchor: str | None = None, path: tuple[str, ...] = ())`. Extend `CrawledDocument` with a
   **last, defaulted** field `sections: tuple[HtmlSection, ...] = ()` (keeps existing
   constructors valid; stays frozen).

2. **NEW `adapters/botting/l6_presentation/html_sections.py`** — pure helpers, no bs4:
   - `SECTION_SEPARATOR = "\n\n"` (single source of truth for joining)
   - `join_section_text(sections) -> str`
   - `section_for_offset(sections, offset) -> HtmlSection | None` (walk cumulative spans
     using the SAME separator; None if empty/out-of-range)
   - `format_location_ref(section, base_url=None) -> str`: anchor → `#<anchor>` (prefixed by
     base_url if given); else breadcrumb `path` joined `" > "`; else `""`.
   - Tests: `tests/test_html_sections.py`.

3. **`adapters/botting/l6_presentation/dom_cleaner.py`** — extend `DomCleaner`, keep
   `clean_html`/`discover_links` working:
   - `_strip_boilerplate(soup, extra_selectors=None)`: `.decompose()` chrome tags
     `script, style, noscript, nav, footer, aside, form` + `[role=navigation|search|banner|
     contentinfo]` + any `extra_selectors` (defensive try/except per selector). Do **not**
     strip `<header>`. Call it at the top of `clean_html` with `selectors.get("boilerplate")`
     (must not change existing test outputs — they have no chrome inside content area).
   - `extract_sections(html, selectors) -> list[HtmlSection]`: strip boilerplate → scope to
     `content_area` (else `main`/`article`/`body`/soup) → walk `h1-h4,p,li` in document order,
     maintaining a `(level, heading)` stack for the breadcrumb `path`; on heading start a new
     section (`anchor` = heading `id` or nearest ancestor `id`); accumulate following `p`/`li`
     text; emit in document order, skip blocks empty in both text and heading.
   - Tests: `tests/test_dom_sections.py` (boilerplate strip removes "JUNK"; anchor from heading
     id; anchor from ancestor id; nested-heading breadcrumb path; `clean_html` regression).

## Feature 2 — scaffold hardening + end-to-end wiring

4. **`scaffolds/base_scaffold.py`** — add `get_boilerplate_selectors(self) -> list[str]` (default `[]`).

5. Harden `get_custom_selectors()` + add `get_boilerplate_selectors()` overrides:
   - `sso_agc_gov_sg.py`: `content_area` → `"#legisContent, .prov1, .body-content, main, article"`;
     `sections` → `".prov1, .prov2, h2, h3, p"`; boilerplate `[".global-nav", ".breadcrumb",
     ".legis-nav", "#toc", ".footer", ".sidebar"]`.
   - `pdpc_gov_sg.py`: `content_area` → `".page-content, main, #content, article"`; boilerplate
     `[".breadcrumb", ".related-content", ".share-bar", ".sidebar", ".footer"]`.
   - `homeaffairs_gov_au.py`: keep `content_area`/`article_links` (test relies on `'main a, #content a'`
     excluding footer `/contact`); boilerplate `[".breadcrumb", ".related-links", ".sidebar",
     ".au-footer", ".cookie-banner"]`.
   - **NEW `scaffolds/pdp_gov_my.py`** — `PDPMyScaffold`, `target_domain = "pdp.gov.my"`
     (Malaysia PDPD; completes AU/SG/MY scoring scope). Register in `scaffold_registry.py`.
   - Extend `tests/test_scaffold_registry.py`: default registry matches `pdp.gov.my`; each
     hardened scaffold has non-empty boilerplate list + a `content_area`.

6. **Wire the flow:**
   - `run.py` `_crawl_one` HTML branch: resolve scaffold selectors for the url, set
     `selectors["boilerplate"] = scaffold.get_boilerplate_selectors()`, call
     `cleaner.extract_sections(result.text, selectors)`, `text = join_section_text(sections)`
     (fall back to `clean_html` if empty), build
     `CrawledDocument(..., is_pdf=False, sections=tuple(sections))`. PDF branch unchanged;
     keep existing try/except + logging.
   - `mock_provision_extractor.py` `_build_finding`: when `doc.sections` non-empty,
     `section = section_for_offset(doc.sections, match.start)` and
     `location_ref = format_location_ref(section, base_url=doc.url) or doc.url or None`;
     else keep `doc.url or None` (PDF behavior identical).
   - Extend `tests/test_mock_provision_extractor.py`: a doc WITH sections (anchor `s26`) →
     finding `location_ref` ends with `#s26`; anchor=None + path set → ends with
     `Part IV > Section 26`; existing no-sections tests unchanged.

## Done criteria
`cd backend && python -m pytest -q` → all green (114 baseline + new). Report the real
pytest tail, files touched, and any deviation.

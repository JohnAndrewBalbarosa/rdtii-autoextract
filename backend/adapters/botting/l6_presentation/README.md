# `l6_presentation/` — Presentation Layer (clean the HTML)

Turns raw HTML into ordered, **anchored, citable** sections and discovers links for crawl
expansion. Pure transformation — no network.

## Files

| File | Role |
|---|---|
| `dom_cleaner.py` | `DomCleaner` — strip boilerplate/chrome, group blocks under headings into sections with anchors + breadcrumb paths, discover links |
| `html_sections.py` | pure helpers: `join_section_text`, `section_for_offset`, `format_location_ref` (the Location Reference field) |

## Cleaning pipeline

```mermaid
flowchart TD
    H([raw HTML]) --> STRIP["strip boilerplate<br/>nav · footer · script · banner<br/>+ scaffold chrome selectors"]
    STRIP --> GROUP["collect blocks (h1–h4, p, li)<br/>group under nearest heading"]
    GROUP --> ANCH["attach anchor + breadcrumb path"]
    ANCH --> FILT["drop short UI widgets<br/>(e.g. 'expand all')"]
    FILT --> SECT(["HtmlSection[]"])
    H --> LINKS["discover_links → PDF + article links"]
    SECT --> LOC["format_location_ref<br/>→ output Location Reference"]
```

The `HtmlSection` shape is the **handoff contract** to Department 02 — do not change it
without coordinating. Owned by **Department 01**
([scraper](../../../../docs/departments/01-scraper/README.md)).

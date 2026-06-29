# `l7_application/` — Application Layer (orchestrate one scrape)

Composes L4 transport + L6 presentation + scaffolds (+ optional LLM) into a single
`scrape_url` use case. Implements `DocumentExtractorPort`.

## Files

| File | Role |
|---|---|
| `pipeline_adapter.py` | `PipelineAdapter.scrape_url(url)` → `ParsedDocument`; optional LLM markdown/JSON structuring via injected `LLMProvider` |

## Orchestration

```mermaid
flowchart TD
    U["scrape_url(url)"] --> SC["ScaffoldRegistry lookup<br/>selectors · keywords · transport"]
    SC --> FE["TransportFactory.fetch_raw"]
    FE --> CL["DomCleaner.extract_sections"]
    CL --> KW{relevant?<br/>scaffold keywords}
    KW --> LLM["(optional) LLMProvider<br/>extract markdown → structure JSON"]
    LLM --> PD(["ParsedDocument<br/>sections · tags · discovered_links"])
    CL --> PD
```

The LLM is the **only AI surface here** and is fully optional — the deterministic path
works without it. Owned by **Department 01**
([scraper](../../../../docs/departments/01-scraper/README.md)).

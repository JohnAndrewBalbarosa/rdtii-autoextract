# `scaffolds/` — Site-Specific Portal Rules

Per-domain extraction rules **without touching the core or the L4/L6/L7 layers.** Adding a
new government portal = one new subclass + one registry line.

## Files

| File | Site / role |
|---|---|
| `base_scaffold.py` | `BaseScaffold` ABC — selectors, boilerplate, keywords, transport type, URL rewrite |
| `scaffold_registry.py` | `ScaffoldRegistry` — domain (substring) → scaffold |
| `sso_agc_gov_sg.py` | Singapore Statutes Online (URL rewrite to PDF view) |
| `pdpc_gov_sg.py` | Singapore PDPC |
| `pdp_gov_my.py` | Malaysia PDP |
| `homeaffairs_gov_au.py` | Australia Home Affairs |
| `legislation_gov_au.py` | Australia Federal Register (Angular SPA → forced dynamic) |

## How a scaffold plugs in

```mermaid
flowchart LR
    URL([URL]) --> R["ScaffoldRegistry<br/>match netloc substring"]
    R --> B["BaseScaffold subclass"]
    B --> T["get_transport_type()<br/>auto / static / dynamic"]
    B --> F["get_fetch_url()<br/>optional rewrite"]
    B --> CS["get_custom_selectors()"]
    B --> BP["get_boilerplate_selectors()"]
    B --> KW["get_keywords()"]
    T --> PA[PipelineAdapter applies them]
    F --> PA
    CS --> PA
    BP --> PA
    KW --> PA
```

To add a portal: subclass `BaseScaffold`, register it, override only what differs, add a
test mirroring `tests/test_legislation_scaffold.py`. Owned by **Department 01**
([scraper](../../../../docs/departments/01-scraper/README.md)).

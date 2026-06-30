# Zetarix token benchmarks

Reproducible, tokenizer-level (`tiktoken cl100k_base`) measurements of the crawler's LLM
token cost. No live model — pure deterministic counting of the exact prompts the pipeline
builds, so anyone can reproduce the numbers from the committed fixture.

## What's here

| Path | What |
|---|---|
| `amortization_benchmark.py` | Tokens-vs-N-pages curve: pipeline (amortized) vs agent tool-calling (flat) |
| `../tools/benchmark_token_paths.py` | Single-page naive-vs-adaptive token comparison |
| `data/inspect_au.html` | The retrieved test page used locally — a real Australian gov law page (~234 KB) |
| `results/amortization_au.json` | Output captured from a local run on `data/inspect_au.html` |

## Reproduce

```bash
cd backend
python benchmarks/amortization_benchmark.py \
  --html benchmarks/data/inspect_au.html \
  --output benchmarks/results/amortization_au.json
```

## Complexity (why the pipeline wins at scale)

For `N` pages, `L` distinct layout families, `k` links/page, skeleton size `S`:

```
T_pipeline(N) = O(1)            link discovery   (once per crawl)
              + O(L · S)        layout learning  (once per layout, reused free)
              + O(N · k)        AI link-judging  (names only — small constant)
              + 0               deterministic extraction (no tokens)
```

- **Average tokens/page = O(L·S / N) + O(k)** → decays like `1/N` toward a small floor
  (the link-judging cost), because layout learning is paid once and reused.
- The agent tool-calling baseline is **O(N · H · T)** — flat-and-high, since the full raw
  HTML (`H`) is re-ingested every page across `T` turns.

## Local result (AU gov page, 77,725 raw-HTML tokens)

| pages | pipeline total | pipeline avg/page | agent total (lo) | cheaper |
|------:|---------------:|------------------:|-----------------:|--------:|
| 1     | 13,310         | 13,310            | 77,725           | 5.8×    |
| 10    | 39,266         | 3,927             | 777,250          | 19.8×   |
| 100   | 298,826        | 2,988             | 7,772,500        | 26.0×   |
| 500   | 1,452,426      | 2,905             | 38,862,500       | 26.8×   |

Pipeline avg/page falls 13,310 → 2,905 (→ the ~2,884 link-judge floor) while the agent
stays at ~77,725/page. The gap widens with scale.

> Note: the per-page floor is the AI link-judging step (judges links by name for accuracy).
> Disable/cache it and the per-page cost trends to 0. See memory: two-scrapers-cost-divergence.

## Measured end-to-end (real crawler, instrumented) — `pipeline_token_test.py`

The numbers above are projections from prompt construction. This test instead **drives the
real `AdaptiveCrawlerAdapter` / `AdaptiveDomainCrawler` code** (the `ScraperOrchestrator`
path) with a token-counting LLM over N same-layout pages and sums the exact tokens the
pipeline actually spends. Reproduce:

```bash
python benchmarks/pipeline_token_test.py --html benchmarks/data/inspect_au.html --pages 100 \
  --output benchmarks/results/pipeline_token_test_au.json
```

Cross-validated by three parallel agents (curve ×2 fixtures + an adversarial verifier).
The pipeline makes **exactly one LLM call total** (layout learned once, then deterministic
reuse), so its token cost is **flat** while the agent baseline scales linearly with pages.

**inspect_au.html** — 77,125 raw-HTML tokens/page:

| pages | pipeline total | avg/page | agent (lo) | cheaper |
|------:|---------------:|---------:|-----------:|--------:|
| 1     | 10,047         | 10,047   | 77,725     | 7.7×    |
| 10    | 10,047         | 1,005    | 777,250    | 77.4×   |
| 100   | 10,047         | 100.5    | 7,772,500  | 773.6×  |
| 500   | 10,047         | 20.1     | 38,862,500 | 3,868×  |

**walkthrough_au.html** — 103,171 raw-HTML tokens/page:

| pages | pipeline total | avg/page | agent (lo) | cheaper |
|------:|---------------:|---------:|-----------:|--------:|
| 1     | 10,072         | 10,072   | 103,771    | 10.3×   |
| 100   | 10,072         | 100.7    | 10,377,100 | 1,030×  |
| 500   | 10,072         | 20.1     | 51,885,500 | 5,151×  |

**Verified mechanism** (independent code audit, `src/zetarix/crawling/adaptive_crawler.py`):
after a layout is cached (`scrape_page:223-226`), a same-fingerprint page reuses the rules
via `_apply_rules` (pure BeautifulSoup, `:297-326`) with **no `self._llm.complete` call** —
per-page extraction is genuinely **0 LLM tokens**. The only LLM calls are link discovery
(`:144`, once/crawl), layout learning (`:282`, once/layout), bounded revision (`:232`,
once/layout), and link relevance (`:340`, crawl path only).

> **Honest caveat (from the adversarial verifier):** the `cheaper` ratios are measured
> against a *naive* agent that re-ingests the full raw HTML every page
> (`pipeline_token_test.py` baseline). A smarter caching/stripping agent would narrow the
> gap — so read these as "vs naive raw-HTML-per-page agent," not a universal constant. The
> architectural claim (per-page extraction = 0 LLM tokens after one-time learning) is real
> and code-verified; the exact multiplier is baseline-dependent.

Raw result data: `results/pipeline_token_test_au.json`, `results/pipeline_token_test_walkthrough.json`,
`results/pipeline_token_test_summary.json`.

## Deterministic quality metrics (no LLM) — `quality_metrics.py`

Quantitative signals that need no live model. Reproduce:

```bash
python benchmarks/quality_metrics.py --output benchmarks/results/quality_metrics.json
```

| fixture | raw→cleaned | raw→skeleton | ms/page | pages/s | fp stability | contaminated |
|---|--:|--:|--:|--:|--:|--:|
| inspect_au.html (77,125 tok) | **−87.4%** | −88.1% | 386 | 2.6 | 100% | no |
| walkthrough_au.html (103,171 tok) | **−90.6%** | −91.1% | 437 | 2.3 | 100% | no |
| test_law.html (100 tok) | −50.0% | −70.0% | 2.8 | 360 | 100% | no |

- **DOM compression:** the cleaner cuts ~87–91% of tokens before anything reaches a model;
  the layout skeleton (`_sample`) cuts ~88–91%. This is why per-page LLM input stays small.
- **Throughput:** deterministic per-page work (fingerprint + clean) is BeautifulSoup-bound at
  ~2.3–2.6 pages/s on 230–315 KB pages (CPU only, no tokens) — a known optimization target
  (switch parser to `lxml`).
- **Fingerprint stability:** 100% — injecting volatile sibling-state classes (`active`,
  `page-2`, `is-open`, …) never changes the fingerprint, so pages of one template share a
  cache entry.
- **Fingerprint collision:** 0 — all 3 distinct fixtures hash to 3 distinct fingerprints, so
  different page types never share (wrong) cached rules.
- **Boilerplate contamination:** 0 terms — no `cookie` / `all rights reserved` / etc. survive
  into cleaned output.

Raw data: `results/quality_metrics.json`.

## Backlog (needs live LLM / real provider / network — tracked as GitHub issues)

Metrics that can't be measured deterministically yet are filed in the **Zetarix Delegation**
project: real-provider token/cost capture, link-judging precision/recall, live crawl
latency + ban-rate, token scaling vs distinct layouts, and OCR/PDF CER. See open issues
labeled `metrics`.

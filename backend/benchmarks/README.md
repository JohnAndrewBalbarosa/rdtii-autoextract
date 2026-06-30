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

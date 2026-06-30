"""Tokens-vs-N-pages amortization benchmark for the Zetarix crawler.

Demonstrates the complexity claim: the deterministic pipeline's AVERAGE LLM tokens per
page decays ~1/N (layout learned once, reused free), approaching a small per-page floor
(AI link-judging on names only), while the agent tool-calling baseline stays flat-and-high
(full raw HTML re-ingested every page). Pure tiktoken counting — no live model, fully
reproducible. Run from backend/:

    python benchmarks/amortization_benchmark.py --html benchmarks/data/inspect_au.html \
        --output benchmarks/results/amortization_au.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig  # noqa: E402
from zetarix.llm.prompt_contracts import (  # noqa: E402
    build_layout_rule_prompt,
    build_link_discovery_prompt,
    build_link_relevance_prompt,
)

# Agent-baseline assumptions (documented so the numbers are defensible).
_AGENT_OVERHEAD = 600          # system prompt + tool schemas, re-sent each turn
_AGENT_REINGEST_TURNS = 2      # fetch -> reason+extract; raw HTML re-billed each turn
_PAGE_GRID = (1, 2, 5, 10, 25, 50, 100, 250, 500)
_OBJECTIVE = CrawlConfig().crawl_objective


def _toks(enc, value: str) -> int:
    return len(enc.encode(value))


def benchmark(html_path: Path, output_path: Path, encoding_name: str) -> dict:
    import tiktoken

    html = html_path.read_text(encoding="utf-8")
    enc = tiktoken.get_encoding(encoding_name)
    url = "https://frozen.example.gov/law"
    soup = BeautifulSoup(html, "html.parser")

    raw_html_tokens = _toks(enc, html)

    # One-time pipeline costs (paid once per crawl / per layout family).
    nav_links = [
        {"url": a.get("href", ""), "text": a.get_text(" ", strip=True)}
        for a in soup.select("nav a[href]")
    ] or [{"url": a.get("href", ""), "text": a.get_text(" ", strip=True)} for a in soup.select("a[href]")[:40]]
    discovery_tokens = _toks(enc, build_link_discovery_prompt(url, nav_links))
    layout_tokens = _toks(enc, build_layout_rule_prompt([AdaptiveDomainCrawler._sample(url, html)]))
    pipeline_one_time = discovery_tokens + layout_tokens

    # Per-page pipeline cost: extraction is deterministic (0 tokens); only AI link-judging
    # spends tokens, and only on link NAMES, not page content.
    candidates = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href and href not in seen:
            seen.add(href)
            candidates.append({"url": href, "name": a.get_text(" ", strip=True)[:160]})
    candidates = candidates[:50]  # realistic in-content link budget per page
    link_judge_tokens = _toks(enc, build_link_relevance_prompt(candidates, _OBJECTIVE)) if candidates else 0
    pipeline_per_page = link_judge_tokens  # extraction = 0

    # Agent baseline per page: overhead + raw HTML, re-ingested across turns.
    agent_per_page_lo = _AGENT_OVERHEAD + raw_html_tokens
    agent_per_page_hi = sum(_AGENT_OVERHEAD + raw_html_tokens for _ in range(_AGENT_REINGEST_TURNS))

    rows = []
    for n in _PAGE_GRID:
        pipe_total = pipeline_one_time + n * pipeline_per_page
        agent_lo = n * agent_per_page_lo
        agent_hi = n * agent_per_page_hi
        rows.append({
            "pages": n,
            "pipeline_total": pipe_total,
            "pipeline_avg_per_page": round(pipe_total / n, 1),
            "agent_total_lo": agent_lo,
            "agent_total_hi": agent_hi,
            "savings_x_vs_agent_lo": round(agent_lo / pipe_total, 1) if pipe_total else None,
        })

    report = {
        "measurement": {
            "kind": "exact_tokenizer_count_not_provider_billing",
            "encoding": encoding_name,
            "input_html": str(html_path),
            "complexity": "T_pipeline(N) = O(1) + O(L*S) + O(N*k); avg/page -> O(L*S/N)+O(k) (1/N decay)",
        },
        "inputs": {
            "raw_html_tokens": raw_html_tokens,
            "pipeline_one_time_tokens": pipeline_one_time,
            "pipeline_per_page_tokens": pipeline_per_page,
            "agent_per_page_tokens_lo": agent_per_page_lo,
            "agent_per_page_tokens_hi": agent_per_page_hi,
            "assumptions": {
                "agent_overhead_per_turn": _AGENT_OVERHEAD,
                "agent_reingest_turns": _AGENT_REINGEST_TURNS,
                "link_candidate_cap": 50,
            },
        },
        "curve": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=Path("benchmarks/data/inspect_au.html"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/amortization_au.json"))
    parser.add_argument("--encoding", default="cl100k_base")
    args = parser.parse_args(argv)
    report = benchmark(args.html, args.output, args.encoding)
    print(f"{'pages':>6} {'pipe_total':>11} {'pipe_avg/pg':>12} {'agent_lo':>11} {'x_cheaper':>10}")
    for r in report["curve"]:
        print(f"{r['pages']:>6} {r['pipeline_total']:>11} {r['pipeline_avg_per_page']:>12} "
              f"{r['agent_total_lo']:>11} {r['savings_x_vs_agent_lo']:>9}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

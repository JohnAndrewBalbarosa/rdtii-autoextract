"""End-to-end token test: drive the REAL crawler and measure LLM tokens it actually spends.

Unlike a projection, this wires a token-counting LLM and a dict fetcher into the actual
`AdaptiveDomainCrawler` / `AdaptiveCrawlerAdapter` code paths, scrapes N same-layout pages,
and sums the exact tiktoken counts of every prompt/response the pipeline sends. It then
compares against the agent-tool-calling baseline (raw HTML re-ingested per page). No live
model, no network — fully reproducible from the committed fixture.

    python benchmarks/pipeline_token_test.py --html benchmarks/data/inspect_au.html \
        --pages 50 --output benchmarks/results/pipeline_token_test_au.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tiktoken  # noqa: E402

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig  # noqa: E402
from zetarix.crawling.adaptive_crawler_adapter import AdaptiveCrawlerAdapter  # noqa: E402

_AGENT_OVERHEAD = 600
_AGENT_REINGEST_TURNS = 2
_ENC = tiktoken.get_encoding("cl100k_base")


def _toks(value: str) -> int:
    return len(_ENC.encode(value))


class TokenCountingLLM:
    """Counts tiktoken(prompt)+tiktoken(response) per call, tagged by agent_profile.

    Returns canned, schema-valid responses so the real pipeline proceeds normally; the
    point is to meter exactly what the crawler sends, not to judge content.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        response = self._respond(agent_profile)
        body = json.dumps(response, separators=(",", ":"))
        self.calls.append({
            "agent_profile": agent_profile,
            "input_tokens": _toks(prompt),
            "output_tokens": _toks(body),
        })
        return response

    @staticmethod
    def _respond(profile: str) -> dict:
        if profile in {"layout_rule_agent", "rule_revision_agent"}:
            return {
                "rules": [
                    {"selector": "script, style, nav, header, footer, aside",
                     "role": "ignore", "reason": "page chrome"},
                    {"selector": "main, article, body",
                     "role": "extract_only", "reason": "main legal content"},
                ],
                "include_url_patterns": [], "exclude_url_patterns": [],
                "confidence": 0.9, "warnings": [],
            }
        if profile == "link_discovery_agent":
            return {"selected_urls": [], "reason": "no nav sampling in token test"}
        if profile == "link_relevance_agent":
            return {"selected_urls": [], "reason": "fallback follows all candidates"}
        return {}


class DictFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def fetch(self, url: str) -> str:
        return self._pages[url]


def run(html_path: Path, pages: int, output_path: Path) -> dict:
    html = html_path.read_text(encoding="utf-8")
    raw_html_tokens = _toks(html)

    # N distinct URLs serving the SAME layout (same fingerprint) with a tiny unique marker,
    # so the crawler learns the layout once and reuses it deterministically thereafter.
    urls = [f"https://gov.example/doc/{i}" for i in range(pages)]
    fetch_map = {u: html.replace("</body>", f"<!-- doc {i} --></body>", 1) for i, u in enumerate(urls)}

    llm = TokenCountingLLM()
    crawler = AdaptiveDomainCrawler(
        DictFetcher(fetch_map), llm,
        robots_allowed=lambda *_: True,
        config=CrawlConfig(min_content_chars=50, max_revision_attempts=0),
    )
    adapter = AdaptiveCrawlerAdapter(crawler)

    extracted_chars = []
    for url in urls:
        doc = adapter.scrape_url(url)
        extracted_chars.append(sum(len(s.text) for s in doc.sections))

    # Per-stage pipeline totals (real, metered).
    by_stage: dict[str, dict] = {}
    for c in llm.calls:
        s = by_stage.setdefault(c["agent_profile"], {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        s["calls"] += 1
        s["input_tokens"] += c["input_tokens"]
        s["output_tokens"] += c["output_tokens"]
    pipeline_total = sum(c["input_tokens"] + c["output_tokens"] for c in llm.calls)

    # Agent tool-calling baseline: raw HTML (re-)ingested per page.
    agent_lo = pages * (_AGENT_OVERHEAD + raw_html_tokens)
    agent_hi = pages * _AGENT_REINGEST_TURNS * (_AGENT_OVERHEAD + raw_html_tokens)

    return {
        "fixture": str(html_path),
        "pages": pages,
        "raw_html_tokens_per_page": raw_html_tokens,
        "pipeline": {
            "llm_calls": len(llm.calls),
            "tokens_total": pipeline_total,
            "tokens_avg_per_page": round(pipeline_total / pages, 1),
            "by_stage": by_stage,
            "per_page_extraction_llm_tokens": 0,
            "extracted_chars_per_page_sample": extracted_chars[0] if extracted_chars else 0,
        },
        "agent_baseline": {
            "tokens_total_lo": agent_lo,
            "tokens_total_hi": agent_hi,
            "tokens_per_page_lo": _AGENT_OVERHEAD + raw_html_tokens,
        },
        "savings": {
            "x_cheaper_vs_agent_lo": round(agent_lo / pipeline_total, 1) if pipeline_total else None,
            "x_cheaper_vs_agent_hi": round(agent_hi / pipeline_total, 1) if pipeline_total else None,
            "pipeline_pct_of_agent_lo": round(100 * pipeline_total / agent_lo, 2) if agent_lo else None,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=Path("benchmarks/data/inspect_au.html"))
    parser.add_argument("--pages", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/pipeline_token_test.json"))
    args = parser.parse_args(argv)
    report = run(args.html, args.pages, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["savings"], indent=2))
    print(f"pipeline {report['pipeline']['tokens_total']} tok over {report['pages']} pages "
          f"({report['pipeline']['tokens_avg_per_page']}/page) vs agent "
          f"{report['agent_baseline']['tokens_total_lo']} tok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproducible tokenizer-level comparison: naive tool path vs adaptive prompts.

This does not claim provider billing usage. It counts the exact tokenized strings sent
through the adaptive prompt contracts under a named tokenizer and records hashes so the
result can be independently reproduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zetarix.cleaning.dom_cleaner import DomCleaner  # noqa: E402
from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler  # noqa: E402
from zetarix.llm.prompt_contracts import (  # noqa: E402
    build_layout_rule_prompt,
    build_link_discovery_prompt,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(encoding, value: str) -> int:
    return len(encoding.encode(value))


def benchmark(html_path: Path, output_path: Path, encoding_name: str) -> dict:
    try:
        import tiktoken
    except ImportError as exc:  # pragma: no cover - environment-specific helper
        raise RuntimeError("Install tiktoken to run this benchmark") from exc

    html = html_path.read_text(encoding="utf-8")
    encoding = tiktoken.get_encoding(encoding_name)
    url = "https://frozen.example.gov/law"
    soup = BeautifulSoup(html, "html.parser")
    nav_links = [
        {"url": anchor.get("href", ""), "text": anchor.get_text(" ", strip=True)}
        for anchor in soup.select("nav a[href]")
    ]

    # A: ordinary deterministic tool path. No model prompt is sent.
    naive_content = DomCleaner().clean_html(html)

    # B: the actual adaptive system prompt contracts, with frozen deterministic outputs.
    discovery_prompt = build_link_discovery_prompt(url, nav_links)
    discovery_output = json.dumps(
        {"selected_urls": [], "reason": "No navigation links in frozen fixture"},
        separators=(",", ":"),
    )
    # Mirror production exactly: the crawler learns layout from a structural skeleton
    # (text stripped, capped at 30k chars) via AdaptiveDomainCrawler._sample — NOT the
    # full raw HTML. Using the real sampler keeps this benchmark honest about the
    # pipeline's actual one-time, amortized structure-analysis cost.
    layout_prompt = build_layout_rule_prompt([AdaptiveDomainCrawler._sample(url, html)])
    layout_output = json.dumps(
        {
            "rules": [
                {"selector": "head", "role": "ignore", "reason": "metadata"},
                {"selector": "body", "role": "extract_only", "reason": "legal content"},
            ],
            "include_url_patterns": [],
            "exclude_url_patterns": [],
            "confidence": 1.0,
            "warnings": [],
        },
        separators=(",", ":"),
    )
    adaptive_content = soup.body.get_text("\n", strip=True) if soup.body else ""
    calls = [
        ("link_discovery", discovery_prompt, discovery_output),
        ("layout_rules", layout_prompt, layout_output),
    ]
    call_rows = [
        {
            "purpose": purpose,
            "input_sha256": _sha256(prompt),
            "output_sha256": _sha256(response),
            "input_tokens": _tokens(encoding, prompt),
            "output_tokens": _tokens(encoding, response),
            "total_tokens": _tokens(encoding, prompt) + _tokens(encoding, response),
        }
        for purpose, prompt, response in calls
    ]
    adaptive_total = sum(row["total_tokens"] for row in call_rows)

    report = {
        "measurement": {
            "kind": "exact_tokenizer_count_not_provider_billing",
            "encoding": encoding_name,
            "input_html": str(html_path),
            "input_html_sha256": _sha256(html),
            "caveat": (
                "Host-agent/tool-call tokens are not exposed. Naive=0 means zero "
                "application LLM API tokens. Provider-reported billing requires a live model. "
                "The layout_rules call is paid ONCE per layout family and reused across all "
                "same-layout pages, so its per-page cost amortizes toward zero at scale; the "
                "link_discovery call is paid once per crawl, not per page."
            ),
        },
        "naive_tool_path": {
            "pipeline": "frozen_html -> DomCleaner",
            "llm_calls": 0,
            "application_llm_tokens": 0,
            "content_sha256": _sha256(naive_content),
            "content_chars": len(naive_content),
            "content": naive_content,
        },
        "adaptive_system_path": {
            "pipeline": "link discovery (once/crawl) -> layout rule (once/layout, skeleton) -> deterministic parser (0 tokens/page)",
            "llm_calls": len(call_rows),
            "calls": call_rows,
            "application_llm_tokens": adaptive_total,
            "amortization_note": (
                "These are one-time setup tokens, not per-page. Over N same-layout pages "
                "the per-page LLM cost trends to 0 (deterministic _apply_rules)."
            ),
            "content_sha256": _sha256(adaptive_content),
            "content_chars": len(adaptive_content),
            "content": adaptive_content,
        },
        "comparison": {
            "additional_application_llm_tokens_for_adaptive": adaptive_total,
            "same_extracted_content": naive_content == adaptive_content,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=Path("test_law.html"))
    parser.add_argument(
        "--output", type=Path, default=Path("out_adaptive_benchmark/token_comparison.json")
    )
    parser.add_argument("--encoding", default="cl100k_base")
    args = parser.parse_args(argv)
    report = benchmark(args.html, args.output, args.encoding)
    print(json.dumps(report["comparison"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

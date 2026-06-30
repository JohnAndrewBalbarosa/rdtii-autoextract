"""CLI for the bounded adaptive domain crawler.

Example:
    python run_adaptive_crawl.py https://www.pdpc.gov.sg --max-pages 5 --max-depth 1
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from zetarix.transport.http_client import HttpClient  # noqa: E402
from zetarix.crawling.adaptive_crawler import (  # noqa: E402
    AdaptiveDomainCrawler,
    CrawlConfig,
)
from zetarix.llm.router import LLMRouter  # noqa: E402


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Learn rules and crawl one website domain.")
    parser.add_argument("seed_url", help="Absolute URL of the website main page.")
    parser.add_argument("--output", default="adaptive_crawl.json", help="JSON output path.")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-revisions", type=int, default=2, choices=(0, 1, 2))
    parser.add_argument("--min-content-chars", type=int, default=80)
    args = parser.parse_args(argv)
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.max_depth < 0:
        parser.error("--max-depth cannot be negative")
    return args


def main(argv=None) -> int:
    args = _parse_args(argv)
    crawler = AdaptiveDomainCrawler(
        HttpClient(),
        LLMRouter.from_env(),
        config=CrawlConfig(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            max_revision_attempts=args.max_revisions,
            min_content_chars=args.min_content_chars,
        ),
    )
    result = crawler.crawl(args.seed_url)
    crawler.write_json(result, args.output)
    print(
        f"[adaptive-crawl] visited={len(result['visited_urls'])} "
        f"extracted={len(result['extracted_pages'])} "
        f"failed={len(result['failed_urls'])} output={args.output}"
    )
    return 0 if result["extracted_pages"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

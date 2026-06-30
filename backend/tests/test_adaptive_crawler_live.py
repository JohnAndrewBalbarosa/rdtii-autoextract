"""Opt-in bounded network smoke test.

Run explicitly with ADAPTIVE_LIVE_SEED set. The deterministic agent isolates live
transport/robots/DOM behavior; normal production runs use LLMRouter.
"""

from __future__ import annotations

import os
import re

import pytest

from zetarix.transport.http_client import HttpClient
from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig


class DeterministicSmokeAgent:
    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "link_discovery_agent":
            urls = list(dict.fromkeys(re.findall(r'https?://[^"\\s]+', prompt)))
            return {"selected_urls": urls[:2], "reason": "bounded live smoke sample"}
        return {
            "rules": [
                {
                    "selector": "script, style, template, noscript, header, footer, nav",
                    "role": "ignore",
                    "reason": "non-content and page chrome",
                },
                {"selector": "main, article, body", "role": "extract_and_crawl", "reason": "smoke-test content"},
            ],
            "include_url_patterns": [],
            "exclude_url_patterns": [r"login|logout|delete|action"],
            "confidence": 0.5,
            "warnings": ["deterministic smoke agent; not production inference"],
        }


@pytest.mark.skipif(not os.environ.get("ADAPTIVE_LIVE_SEED"), reason="opt-in live test")
def test_bounded_live_seed():
    seed = os.environ["ADAPTIVE_LIVE_SEED"]
    crawler = AdaptiveDomainCrawler(
        HttpClient(max_retries=0, domain_throttle=0),
        DeterministicSmokeAgent(),
        config=CrawlConfig(max_depth=0, max_pages=1, max_revision_attempts=0, min_content_chars=20),
    )
    result = crawler.crawl(seed)
    assert len(result["visited_urls"]) <= 1
    assert set(result) == {
        "visited_urls", "skipped_urls", "failed_urls", "extracted_pages", "learned_layouts"
    }
    assert result["extracted_pages"], result

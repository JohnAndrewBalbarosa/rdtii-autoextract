from __future__ import annotations

import gzip
import zlib

from adapters.botting.l7_application.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig
from adapters.botting.l4_transport.http_client import _decode_content_encoding


HOME = """
<html><body><header><nav>
  <a href='/laws'>Laws</a><a href='/guidance'>Guidance</a>
  <a href='https://other.example/out'>External</a><a href='/login'>Login</a>
</nav></header><main><h1>Regulator</h1><p>Official regulatory portal.</p></main></body></html>
"""

LAW = """
<html><body><header><nav><a href='/'>Home</a></nav></header>
<main class='legal-content'><h1>Data Protection Act</h1>
<p>Personal data transfers require safeguards and documented accountability measures.</p>
<h2><a href='/laws/section-2'>Section 2</a></h2></main>
<footer>All rights reserved</footer></body></html>
"""

SECTION = """
<html><body><main class='legal-content'><h1>Section 2</h1>
<p>An organisation must protect personal data using reasonable security arrangements.</p>
</main></body></html>
"""


class FakeFetcher:
    pages = {
        "https://example.gov/": HOME,
        "https://example.gov/laws": LAW,
        "https://example.gov/guidance": LAW,
        "https://example.gov/laws/section-2": SECTION,
    }

    def fetch(self, url: str) -> str:
        return self.pages[url]


class FakeLLM:
    def __init__(self, revise: bool = False):
        self.revise = revise
        self.revisions = 0

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "link_discovery_agent":
            return {
                "selected_urls": [
                    "https://example.gov/laws",
                    "https://example.gov/guidance",
                    "https://other.example/out",
                ],
                "reason": "representative top-level sections",
            }
        if agent_profile == "rule_revision_agent":
            self.revisions += 1
            return self._good_rules()
        if self.revise:
            return {
                "rules": [{"selector": ".missing", "role": "extract_only", "reason": "candidate"}],
                "include_url_patterns": [],
                "exclude_url_patterns": [],
                "confidence": 0.2,
                "warnings": [],
            }
        return self._good_rules()

    @staticmethod
    def _good_rules():
        return {
            "rules": [
                {"selector": "header, footer", "role": "ignore", "reason": "boilerplate"},
                {"selector": "main", "role": "extract_and_crawl", "reason": "primary content"},
            ],
            "include_url_patterns": [r"/laws"],
            "exclude_url_patterns": [r"/login"],
            "confidence": 0.9,
            "warnings": [],
        }


def make_crawler(llm=None, **config):
    return AdaptiveDomainCrawler(
        FakeFetcher(),
        llm or FakeLLM(),
        robots_allowed=lambda _url, _agent: True,
        config=CrawlConfig(min_content_chars=40, **config),
    )


def test_crawl_learns_roles_and_stays_on_domain():
    result = make_crawler(max_depth=2, max_pages=5).crawl("https://example.gov")

    assert "https://example.gov/laws" in result["visited_urls"]
    assert "https://other.example/out" not in result["visited_urls"]
    assert any(page["source_url"].endswith("section-2") for page in result["extracted_pages"])
    assert all("All rights reserved" not in page["content"] for page in result["extracted_pages"])
    roles = {
        rule["role"]
        for layout in result["learned_layouts"]
        for rule in layout["rules"]["rules"]
    }
    assert {"ignore", "extract_and_crawl"} <= roles


def test_invalid_rules_are_revised_at_most_twice():
    llm = FakeLLM(revise=True)
    result = make_crawler(llm, max_depth=1, max_pages=2, max_revision_attempts=2).crawl(
        "https://example.gov/"
    )

    assert llm.revisions >= 1
    assert llm.revisions <= 2 * len(result["learned_layouts"])
    assert result["extracted_pages"]
    assert result["extracted_pages"][0]["extraction_method"] == "ai_rules"


def test_robots_disallow_stops_before_fetch():
    crawler = AdaptiveDomainCrawler(
        FakeFetcher(),
        FakeLLM(),
        robots_allowed=lambda _url, _agent: False,
    )
    result = crawler.crawl("https://example.gov/")

    assert result["visited_urls"] == []
    assert result["skipped_urls"] == [
        {"url": "https://example.gov/", "reason": "robots_disallowed"}
    ]


def test_canonicalization_removes_fragment_tracking_and_duplicate_slashes():
    canonical = AdaptiveDomainCrawler._canonicalize(
        "HTTPS://WWW.Example.Gov//laws/?utm_source=x&b=2&a=1#part"
    )
    assert canonical == "https://www.example.gov/laws?a=1&b=2"


def test_http_content_encoding_decoder_supports_advertised_encodings():
    body = b"<html><body>Law</body></html>"
    assert _decode_content_encoding(gzip.compress(body), "gzip") == body
    assert _decode_content_encoding(zlib.compress(body), "deflate") == body

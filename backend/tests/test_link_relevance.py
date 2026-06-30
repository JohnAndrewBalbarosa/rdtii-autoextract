"""AI judges in-page links by NAME (anchor text + URL) before following them.

The user prioritizes accuracy over tokens: rather than a deterministic regex allow-list,
an LLM decides which discovered links are worth scraping based on their name and the
crawl objective. It degrades to following all candidates when the LLM doesn't participate,
so it never silently loses links on error.
"""

from __future__ import annotations

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig


def _crawler(llm):
    return AdaptiveDomainCrawler(object(), llm, robots_allowed=lambda *_: True,
                                 config=CrawlConfig())


CANDIDATES = [
    {"url": "https://x.gov/laws", "name": "Laws & Regulations"},
    {"url": "https://x.gov/careers", "name": "Careers"},
]


def test_keeps_only_ai_approved_links():
    class LLM:
        def complete(self, prompt, schema, agent_profile="main_controller"):
            assert agent_profile == "link_relevance_agent"
            # The prompt must carry the names so the model can judge by name.
            assert "Laws & Regulations" in prompt and "Careers" in prompt
            return {"selected_urls": ["https://x.gov/laws"], "reason": "law-related by name"}

    assert _crawler(LLM())._select_useful_links(CANDIDATES, "laws") == ["https://x.gov/laws"]


def test_falls_back_to_all_candidates_when_llm_omits_selection():
    class LLM:
        def complete(self, *a, **k):
            return {"rules": []}  # malformed for this purpose: no selected_urls

    got = _crawler(LLM())._select_useful_links(CANDIDATES, "laws")
    assert got == ["https://x.gov/laws", "https://x.gov/careers"]


def test_falls_back_on_llm_error():
    class LLM:
        def complete(self, *a, **k):
            raise RuntimeError("model down")

    got = _crawler(LLM())._select_useful_links(CANDIDATES, "laws")
    assert got == ["https://x.gov/laws", "https://x.gov/careers"]


def test_drops_hallucinated_urls_not_in_candidates():
    class LLM:
        def complete(self, *a, **k):
            return {"selected_urls": ["https://evil.com/x", "https://x.gov/laws"], "reason": ""}

    assert _crawler(LLM())._select_useful_links(CANDIDATES, "laws") == ["https://x.gov/laws"]

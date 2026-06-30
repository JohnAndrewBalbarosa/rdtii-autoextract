"""_sample() must hand the layout-learning LLM a structural skeleton, not page text.

Sending body text into the layout-rule prompt leaks document content into the model
context and bloats the prompt for no benefit — selectors are inferred from structure.
See memory: two-scrapers-cost-divergence.
"""

from __future__ import annotations

from adapters.botting.l7_application.adaptive_crawler import AdaptiveDomainCrawler

HTML = (
    "<html><body><main class='legal-content' id='doc'>"
    "<h1>Secret Title</h1><p>Confidential body text here.</p></main>"
    "<script>var x = 1;</script></body></html>"
)


def test_sample_keeps_structure_and_drops_body_text():
    excerpt = AdaptiveDomainCrawler._sample("https://x.gov/a", HTML)["html_excerpt"]

    # Structural signals the selector model needs survive.
    assert "legal-content" in excerpt
    assert "id=\"doc\"" in excerpt or "id='doc'" in excerpt
    assert "<main" in excerpt and "<h1" in excerpt

    # Page text and scripts must NOT reach the model.
    assert "Secret Title" not in excerpt
    assert "Confidential body text" not in excerpt
    assert "<script" not in excerpt

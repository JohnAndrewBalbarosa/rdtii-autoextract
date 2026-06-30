"""Layout fingerprint = stable-class-set hash (approach b), NOT a template heuristic.

The fingerprint decides cache hit/miss: same template + different content must hash the
same (cache hit → 0 extra LLM call), while a genuinely different page-type must hash
differently (cache miss → AI re-learns, by design — accuracy over token savings). A
volatile-token filter keeps active/selected/index/hash classes from drifting the hash
between sibling pages. See memory: two-scrapers-cost-divergence.
"""

from __future__ import annotations

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig

# Same template (div.quote list), different content + volatile state classes.
QUOTES_P1 = """<html><body><main class='container'>
<div class='quote'><span class='text'>A</span><a class='tag active' href='/t/a'>a</a></div>
<div class='quote'><span class='text'>B</span><a class='tag' href='/t/b'>b</a></div>
<nav class='pager'><a class='page-1 current' href='/p/1'>1</a></nav></main></body></html>"""

QUOTES_P2 = """<html><body><main class='container'>
<div class='quote'><span class='text'>C</span><a class='tag' href='/t/c'>c</a></div>
<div class='quote'><span class='text'>D</span><a class='tag active' href='/t/d'>d</a></div>
<nav class='pager'><a class='page-2 current' href='/p/2'>2</a></nav></main></body></html>"""

# Different page-type: different class vocabulary entirely.
ABOUT = """<html><body><main class='about-page'>
<section class='bio'><h1>About</h1><p class='lead'>Hello.</p></section></main></body></html>"""


def _crawler():
    return AdaptiveDomainCrawler(object(), object(), robots_allowed=lambda *_: True,
                                 config=CrawlConfig())


def test_same_template_different_content_yields_same_fingerprint():
    fp1, _ = _crawler()._layout_fingerprint(QUOTES_P1)
    fp2, _ = _crawler()._layout_fingerprint(QUOTES_P2)
    assert fp1 == fp2  # volatile classes (active, page-N, current) ignored


def test_different_page_type_yields_different_fingerprint():
    fp_quotes, _ = _crawler()._layout_fingerprint(QUOTES_P1)
    fp_about, _ = _crawler()._layout_fingerprint(ABOUT)
    assert fp_quotes != fp_about


def test_fingerprint_uses_stable_class_set_not_repeat_counting():
    # Approach (b): the signature is the SET of stable classes, so repeating div.quote
    # 2x vs 5x must not change the fingerprint (no count-based template heuristic).
    five = QUOTES_P1.replace(
        "</nav>",
        "</nav>" + "<div class='quote'><span class='text'>E</span></div>" * 3,
    )
    fp_two, payload = _crawler()._layout_fingerprint(QUOTES_P1)
    fp_five, _ = _crawler()._layout_fingerprint(five)
    assert fp_two == fp_five
    assert "stable_classes" in payload and "quote" in payload["stable_classes"]

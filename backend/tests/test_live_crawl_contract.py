from __future__ import annotations

import json
import logging
import os

import run
from zetarix.cleaning.dom_cleaner import DomCleaner
from zetarix.extraction.rule_based_provision_extractor import RuleBasedProvisionExtractor
from zetarix.transport.fetch_result import FetchResult


SEED_URL = "https://example.gov/privacy"
LEGAL_URL = "https://example.gov/privacy/text/original/document_1.html"

SEED_HTML = """
<html><body>
  <header>
    <nav>
      <a href="/privacy">Home</a>
      <a href="/privacy?utm_source=newsletter">Privacy home duplicate</a>
      <a href="/contact">Contact</a>
      <a href="/privacy-statement">Privacy Statement</a>
    </nav>
  </header>
  <main>
    <h1>Privacy portal</h1>
    <p>Skip to main content</p>
    <p>
      This ministry portal provides official access to privacy legislation, legal
      text, authorised versions, regulatory guidance, and cross-border data
      protection materials for public consultation and compliance review.
    </p>
    <p>
      Use the official legislation text asset below rather than the homepage for
      article-level legal analysis.
    </p>
    <iframe src="/privacy/text/original/document_1.html" title="Legislation text"></iframe>
    <a href="/privacy/text/original/document_1.html">Open act text</a>
    <a href="/privacy/text/original/document_1.html?utm_source=portal">Open act text duplicate</a>
  </main>
</body></html>
"""

LEGAL_HTML = """
<html><body>
  <h1>Privacy Act 1988</h1>
  <p class="TOC5">13D Overseas act required by foreign law</p>
  <p class="TOC5">16C Acts and practices of overseas recipients of personal information</p>
  <p class="Header">Contents</p>
  <h2>13D Overseas act required by foreign law</h2>
  <p>
    An act or practice done overseas is not an interference with privacy if it is
    required by an applicable foreign law.
  </p>
  <h2>16C Acts and practices of overseas recipients of personal information</h2>
  <p>
    If an APP entity discloses personal information to an overseas recipient, the
    organisation remains accountable for the handling of that personal information.
  </p>
  <p class="ENoteTableText">Endnote 5</p>
</body></html>
"""


class FakeFetcher:
    pages = {
        SEED_URL: FetchResult(
            url=SEED_URL,
            status=200,
            content_type="text/html; charset=utf-8",
            body=SEED_HTML.encode("utf-8"),
        ),
        LEGAL_URL: FetchResult(
            url=LEGAL_URL,
            status=200,
            content_type="text/html; charset=utf-8",
            body=LEGAL_HTML.encode("utf-8"),
        ),
    }

    def fetch_raw(self, url: str) -> FetchResult:
        if url in {
            "https://example.gov/privacy?utm_source=newsletter",
            "https://example.gov/privacy/",
            "https://example.gov/privacy-statement",
        }:
            return self.pages[SEED_URL]
        if url == "https://example.gov/privacy/text/original/document_1.html?utm_source=portal":
            return self.pages[LEGAL_URL]
        return self.pages[url]


def test_dom_cleaner_removes_navigation_toc_and_endnotes_but_keeps_bare_sections():
    cleaned = DomCleaner().clean_html(LEGAL_HTML)

    assert "Contents" not in cleaned
    assert "Endnote 5" not in cleaned
    assert "13D Overseas act required by foreign law" in cleaned
    assert "16C Acts and practices of overseas recipients of personal information" in cleaned
    assert "personal information to an overseas recipient" in cleaned


def test_dom_cleaner_can_log_kept_and_removed_tags(monkeypatch, caplog):
    monkeypatch.setenv("ZETARIX_DEBUG_DOM", "1")
    caplog.set_level(logging.INFO)

    DomCleaner().clean_html(LEGAL_HTML)

    message = next(record.getMessage() for record in caplog.records if "DomCleaner content_selector=" in record.getMessage())
    assert "kept_tags=" in message
    assert "skipped=" in message
    assert "preview=" in message


def test_live_crawl_prefers_discovered_legal_asset_over_seed_homepage():
    logger = logging.getLogger("test.live-crawl")
    docs = run._crawl_seed_documents(SEED_URL, "Australia", FakeFetcher(), logger)

    assert docs, "expected discovered legal documents from the live crawl path"
    assert all(doc.url == LEGAL_URL for doc in docs)
    assert len(docs) == 1
    assert all("skip to main" not in doc.text.lower() for doc in docs)
    assert any("16C Acts and practices of overseas recipients" in doc.text for doc in docs)


def test_live_main_does_not_fall_back_to_gold_when_live_crawl_succeeds(tmp_path, monkeypatch):
    out_dir = str(tmp_path / "out")
    monkeypatch.setattr(run, "_seed_urls", lambda *args, **kwargs: [SEED_URL])
    monkeypatch.setattr(run, "tag_discovery", lambda findings, docs_dir=None: findings)

    def fail_gold(*args, **kwargs):
        raise AssertionError("gold fallback should not be used when live crawl succeeds")

    monkeypatch.setattr(run, "build_gold_findings", fail_gold)

    code = run.main(
        ["--country", "AU", "--pillar", "6", "--source", "live", "--out-dir", out_dir],
        fetcher=FakeFetcher(),
        extractor=RuleBasedProvisionExtractor(),
    )

    assert code == 0

    with open(os.path.join(out_dir, "output.json"), encoding="utf-8") as handle:
        payload = json.load(handle)

    sources = [prov["source_url"] for item in payload for prov in item["provisions"]]
    verbatims = [prov["verbatim"] for item in payload for prov in item["provisions"]]
    rationales = [prov["mapping_rationale"] for item in payload for prov in item["provisions"]]

    assert payload, "live run should emit findings when discovery succeeds"
    assert all(url == LEGAL_URL for url in sources)
    assert all("Privacy portal" not in text for text in verbatims)
    assert any("Overseas act required by foreign law" in text for text in verbatims)
    assert all("exact section text here" not in text.lower() for text in verbatims)
    assert all("keyword" not in text.lower() for text in rationales)

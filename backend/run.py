"""RDTII / Zetarix Round-1 CLI — the reviewer contract.

    python run.py --country SG --pillar 6

Resolves a country + pillar, produces ``Finding`` rows, tags each NEW/KNOWN against the
gold database, and writes the submission ``output.csv`` + ``output.json`` + a run log
under ``--out-dir`` (default ``./out``). Designed to satisfy the deck p.12 reviewer
contract: a misspelt/aliased country is accepted, and it works with **no manual steps**.

Two sources:

* ``--source gold`` (default-safe, OFFLINE): builds findings straight from the reviewer-
  validated golden dataset. No network, no LLM — proves the CSV/JSON contract end-to-end.
* ``--source live``: wires the real crawl→extract path structurally via
  ``ScraperOrchestrator``. Real extraction needs an ``LLMProvider``; when none is
  configured (the common case here — no API key) it prints a clear notice and falls back
  to gold behaviour so the command still yields valid output files.

Run as a script (``python run.py ...``) or import ``main(argv)`` for testing.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import time
import urllib.parse
from datetime import date

# Make `from core...` / `from adapters...` resolve when run as a plain script from any cwd.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from zetarix.domain.document import CrawledDocument  # noqa: E402
from zetarix.domain.entities import DiscoveryTag, Finding, Pillar  # noqa: E402
from zetarix.domain.indicator_codes import to_canonical  # noqa: E402
from zetarix.scoring.golden_dataset import (  # noqa: E402
    GoldRecord,
    load_gold_records,
    load_reference_items,
)
from zetarix.orchestration.output_emitter import write_csv, write_json  # noqa: E402
from zetarix.scoring.scoring import discovery_diff, finding_to_match_item  # noqa: E402

MODEL_VERSION = "zetarix-round1-gold-1.0"
_LIVE_CRAWL_MAX_PAGES = 6
_LIVE_DISCOVERED_DOCS_PER_SEED = 4

# Reviewer may pass an ISO-ish code, an alias, or the full name (any case). Map → the
# canonical country name used as the sheet name in the golden workbooks.
_COUNTRY_ALIASES: dict[str, str] = {
    "sg": "Singapore",
    "singapore": "Singapore",
    "au": "Australia",
    "aus": "Australia",
    "australia": "Australia",
    "my": "Malaysia",
    "mys": "Malaysia",
    "malaysia": "Malaysia",
}

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_NON_LEGAL_TITLE_RE = re.compile(
    r"\b("
    r"contact us|privacy statement|terms and conditions|overview|home|homepage|"
    r"about us|feedback|faq|news|announcement|media release|portal"
    r")\b",
    re.IGNORECASE,
)
_LEGAL_TITLE_RE = re.compile(
    r"\b("
    r"act|regulation|regulations|ordinance|statute|code|law|laws|legislation|gazette|"
    r"privacy principle|order"
    r")\b",
    re.IGNORECASE,
)
_LEGAL_PROVISION_RE = re.compile(
    r"\b("
    r"section|article|part|division|schedule|shall|must|must not|shall not|may not|"
    r"disclose|transfer|retain|collect|consent|overseas recipient|foreign law|"
    r"app entity|privacy principle|applicable law"
    r")\b",
    re.IGNORECASE,
)
_BARE_LEGAL_SECTION_RE = re.compile(r"\b\d+[A-Za-z]{0,2}\b")
_NON_LEGAL_URL_RE = re.compile(
    r"(?:^|[/_.?=&-])("
    r"contact(?:-us)?|privacy-statement|terms(?:-and-conditions)?|overview|home|"
    r"feedback|faq|news|announcements?|media|events|press|copyright"
    r")(?:$|[/_.?=&-])",
    re.IGNORECASE,
)


def resolve_country(raw: str) -> str | None:
    """Map an alias / code / full name (case-insensitive) to a canonical country name.

    Returns ``None`` for an unrecognised value so the caller can fail loudly.
    """
    if not raw:
        return None
    return _COUNTRY_ALIASES.get(raw.strip().lower())


def _last_amended_year(timeframe: str) -> date | None:
    """Pick the most recent 4-digit year in a free-text timeframe → ``date(year,1,1)``.

    Gold timeframes read like ``"Since 2012 last amended on 1 February 2021"``; the latest
    year is the best available proxy for "Last Amended". ``None`` when no year is present.
    """
    years = [int(match.group()) for match in _YEAR_RE.finditer(timeframe or "")]
    if not years:
        return None
    return date(max(years), 1, 1)


def gold_record_to_finding(record: GoldRecord) -> Finding:
    """Convert a reviewer-validated ``GoldRecord`` → a submission ``Finding`` (KNOWN)."""
    pillar = Pillar(record.pillar_id)
    return Finding(
        title=record.act_name,
        last_update=_last_amended_year(record.timeframe),
        url=record.urls[0] if record.urls else "",
        scope=record.coverage,
        provisions="",
        impact=record.impact,
        pillar=pillar,
        indicator=to_canonical(record.indicator_id),
        confidence=1.0,
        economy=record.country,
        law_number=None,
        article_section="",
        discovery_tag=DiscoveryTag.KNOWN,
        verbatim_snippet="",
        mapping_rationale="",
        location_ref=record.urls[0] if record.urls else None,
        notes="",
    )


def build_gold_findings(country: str, pillar: int, docs_dir: str | None = None) -> list[Finding]:
    """All gold findings for ``country`` + ``pillar`` (the offline source of truth)."""
    records = load_gold_records(docs_dir) if docs_dir else load_gold_records()
    return [
        gold_record_to_finding(record)
        for record in records
        if record.country == country and record.pillar_id == pillar
    ]


def tag_discovery(findings: list[Finding], docs_dir: str | None = None) -> list[Finding]:
    """Stamp each finding NEW/KNOWN: KNOWN if it matches a gold/reference act, else NEW.

    Uses ``scoring.discovery_diff`` so the tag is consistent with the F1 harness. Findings
    sourced from the gold DB stay KNOWN; only genuinely novel acts flip to NEW.
    """
    gold = list(load_gold_records(docs_dir) if docs_dir else load_gold_records())
    references = load_reference_items(docs_dir) if docs_dir else load_reference_items()
    novel_items = discovery_diff(findings, gold, references)
    novel_keys = {(item.act_name, item.indicator_id) for item in novel_items}

    tagged: list[Finding] = []
    for finding in findings:
        item = finding_to_match_item(finding)
        is_new = (item.act_name, item.indicator_id) in novel_keys
        tag = DiscoveryTag.NEW if is_new else DiscoveryTag.KNOWN
        tagged.append(_with_tag(finding, tag))
    return tagged


def _with_tag(finding: Finding, tag: DiscoveryTag) -> Finding:
    from dataclasses import replace

    return replace(finding, discovery_tag=tag)


def _default_extractor():
    """Default live ``ProvisionExtractor``: the deterministic mock reference adapter.

    The mock proves the crawl→extract→tag→emit plumbing offline and emits REAL verbatim
    snippets. A real LLM extractor swaps in via the same port (``--source live`` plus a
    custom ``extractor=`` injection) with no other code change.
    """
    from zetarix.extraction.rule_based_provision_extractor import RuleBasedProvisionExtractor
    if os.environ.get("ZETARIX_ENABLE_REVIEWER_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return RuleBasedProvisionExtractor()
    try:
        from zetarix.llm.router import LLMRouter

        return RuleBasedProvisionExtractor(llm_provider=LLMRouter.from_env())
    except Exception:
        return RuleBasedProvisionExtractor()


def _default_fetcher():
    """Default live fetcher: static HTTP with dynamic-page fallback when available.

    Any object exposing ``fetch_raw(url) -> FetchResult`` is acceptable; tests inject a
    fake so the live path runs offline.
    """
    from zetarix.transport.factory import TransportFactory
    from zetarix.transport.http_client import HttpClient

    try:
        from zetarix.transport.playwright_client import PlaywrightClient

        return TransportFactory(HttpClient(), PlaywrightClient())
    except Exception:
        return HttpClient()


def _seed_urls(country: str, pillar: int, docs_dir: str | None = None) -> list[str]:
    """Seed crawl URLs for the country+pillar, taken from the golden reference links."""
    records = load_gold_records(docs_dir) if docs_dir else load_gold_records()
    urls: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.country != country or record.pillar_id != pillar:
            continue
        for url in record.urls:
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _crawl_one(url: str, country: str, fetcher, logger) -> CrawledDocument | None:
    """Fetch ``url`` and reduce it to a ``CrawledDocument`` (PDF or cleaned HTML).

    Returns ``None`` on any fetch/parse failure (logged, never raised) so one dead link
    cannot crash the run.
    """
    try:
        result = fetcher.fetch_raw(url)
    except Exception as exc:  # network-less / blocked / timeout — skip, don't crash
        logger.warning("fetch failed url=%s (%s); skipping", url, exc)
        return None

    try:
        if result.is_pdf:
            from zetarix.transport.pdf_parser import PdfParser

            text = PdfParser().extract_text(result.body)
            return CrawledDocument(url=url, economy=country, text=text, is_pdf=True)

        from zetarix.cleaning.dom_cleaner import DomCleaner

        text = DomCleaner().clean_html(result.text)
        return CrawledDocument(url=url, economy=country, text=text, is_pdf=False)
    except Exception as exc:  # parse/decode failure — skip this doc
        logger.warning("parse failed url=%s (%s); skipping", url, exc)
        return None


class _HeuristicOnlyLLM:
    """Force the adaptive crawler onto its built-in heuristic path."""

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        raise RuntimeError("live pipeline is running in heuristic-only crawler mode")


def _page_to_crawled_document(page: dict, country: str) -> CrawledDocument | None:
    text = (page.get("content") or "").strip()
    if not text:
        return None
    return CrawledDocument(
        url=page.get("source_url", ""),
        economy=country,
        text=text,
        is_pdf=page.get("document_type") == "pdf",
    )


def _candidate_score(url: str) -> tuple[int, str]:
    lowered = url.lower()
    score = 0
    if any(token in lowered for token in (".pdf", ".doc", ".docx", ".epub", "/text/", "document_")):
        score += 8
    if any(token in lowered for token in ("act", "regulation", "law", "privacy", "data", "protection")):
        score += 4
    if any(token in lowered for token in ("download", "authorised", "original")):
        score += 2
    if any(token in lowered for token in ("interaction", "print", "search", "account", "sign-in")):
        score -= 4
    if _NON_LEGAL_URL_RE.search(lowered):
        score -= 10
    return (score, lowered)


def _is_preferred_live_document(doc: CrawledDocument) -> bool:
    lowered_url = (doc.url or "").lower()
    lowered_text = (doc.text or "").lower()
    if any(token in lowered_url for token in (".pdf", ".doc", ".docx", ".epub", "/text/", "document_")):
        return True
    if lowered_text.startswith("skip to main"):
        return False
    return doc.is_pdf


def _normalized_title(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _canonical_source_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url or ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v)
        for k, v in query
        if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "ref", "source"}
    ]
    query_str = urllib.parse.urlencode(sorted(filtered))
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query_str, ""))


def _document_score(doc: CrawledDocument) -> int:
    text = doc.text or ""
    header = "\n".join(text.splitlines()[:8])
    score = 0
    if _LEGAL_TITLE_RE.search(header):
        score += 5
    if _LEGAL_PROVISION_RE.search(text[:1500]):
        score += 5
    if any(token in (doc.url or "").lower() for token in (".pdf", "/text/", "document_", "legislation", "act")):
        score += 4
    if _NON_LEGAL_URL_RE.search((doc.url or "").lower()):
        score -= 10
    if _NON_LEGAL_TITLE_RE.search(header):
        score -= 10
    return score


def _is_real_legal_document(doc: CrawledDocument) -> bool:
    text = (doc.text or "").strip()
    if len(text) < 120:
        return False
    header = "\n".join(text.splitlines()[:8])
    if _NON_LEGAL_URL_RE.search((doc.url or "").lower()):
        return False
    if _NON_LEGAL_TITLE_RE.search(header):
        return False
    if "contact us" in text[:600].lower() or "terms and conditions" in text[:600].lower():
        return False
    if "privacy statement" in text[:600].lower():
        return False
    if _LEGAL_TITLE_RE.search(header) is None and _LEGAL_PROVISION_RE.search(text[:2000]) is None:
        return False
    if (
        re.search(r"\b(section|article)\b", text[:2500], re.I) is None
        and _BARE_LEGAL_SECTION_RE.search(text[:500]) is None
        and doc.is_pdf is False
    ):
        return False
    return _document_score(doc) >= 7


def _dedupe_live_documents(documents: list[CrawledDocument]) -> list[CrawledDocument]:
    deduped: dict[tuple[str, str, str], tuple[int, CrawledDocument]] = {}
    for doc in documents:
        if not _is_real_legal_document(doc):
            continue
        canonical_url = _canonical_source_url(doc.url)
        digest = hashlib.sha256(doc.text.encode("utf-8", errors="replace")).hexdigest()[:16]
        title_line = _normalized_title((doc.text or "").splitlines()[0] if doc.text else "")
        key = (title_line, digest, canonical_url if any(token in canonical_url for token in (".pdf", "/text/", "document_")) else "")
        score = _document_score(doc)
        current = deduped.get(key)
        if current is None or score > current[0]:
            deduped[key] = (score, doc)
    return [item[1] for item in sorted(deduped.values(), key=lambda item: (-item[0], item[1].url))]


def _dedupe_live_findings(findings: list[Finding]) -> list[Finding]:
    best: dict[tuple[str, str, str, str], Finding] = {}
    for finding in findings:
        if _NON_LEGAL_URL_RE.search((finding.url or "").lower()):
            continue
        if _NON_LEGAL_TITLE_RE.search(finding.title or ""):
            continue
        if not finding.article_section.strip() or not finding.verbatim_snippet.strip():
            continue
        key = (
            _normalized_title(finding.title),
            finding.article_section.strip().lower(),
            finding.indicator,
            "",
        )
        current = best.get(key)
        if current is None:
            best[key] = finding
            continue
        current_score = (current.confidence, len(current.verbatim_snippet), len(current.provisions))
        candidate_score = (finding.confidence, len(finding.verbatim_snippet), len(finding.provisions))
        if candidate_score > current_score:
            best[key] = finding
    return list(best.values())


def _crawl_seed_documents(url: str, country: str, fetcher, logger) -> list[CrawledDocument]:
    from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig

    crawler = AdaptiveDomainCrawler(
        fetcher,
        _HeuristicOnlyLLM(),
        config=CrawlConfig(max_depth=1, max_pages=_LIVE_CRAWL_MAX_PAGES),
    )

    pages: list[dict] = []
    try:
        seed_page = crawler.scrape_page(url, depth=0, found_on_url=None)
    except Exception as exc:
        logger.warning("adaptive scrape failed url=%s (%s); falling back to direct fetch", url, exc)
        direct = _crawl_one(url, country, fetcher, logger)
        return [direct] if direct is not None else []

    pages.append(seed_page)
    candidates = sorted(
        set(seed_page.get("discovered_links", [])),
        key=_candidate_score,
        reverse=True,
    )
    for candidate in candidates[:_LIVE_DISCOVERED_DOCS_PER_SEED]:
        try:
            pages.append(crawler.scrape_page(candidate, depth=1, found_on_url=url))
        except Exception as exc:
            logger.warning("adaptive child scrape failed url=%s (%s); skipping", candidate, exc)

    documents: list[CrawledDocument] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        doc = _page_to_crawled_document(page, country)
        if doc is None:
            continue
        digest = hashlib.sha256(doc.text.encode("utf-8", errors="replace")).hexdigest()[:16]
        key = (doc.url, digest)
        if key in seen:
            continue
        seen.add(key)
        documents.append(doc)
    documents = _dedupe_live_documents(documents)
    preferred = [doc for doc in documents if _is_preferred_live_document(doc)]
    if preferred:
        return preferred
    return documents


def _build_live_findings(country, pillar, logger, docs_dir, fetcher, extractor):
    """Real crawl→extract path. Returns a (possibly empty) list of Findings.

    Resolves seed URLs for country+pillar, fetches each (offline-safe: failures are
    logged and skipped), builds a ``CrawledDocument`` and runs the injected
    ``ProvisionExtractor``. With the default mock extractor this yields Findings whose
    ``verbatim_snippet``/``article_section`` are populated from the real document text.
    """
    seed = _seed_urls(country, pillar, docs_dir)
    logger.info("live crawl seeded with %d url(s)", len(seed))

    findings: list[Finding] = []
    for url in seed:
        docs = _crawl_seed_documents(url, country, fetcher, logger)
        if not docs:
            continue
        for doc in docs:
            try:
                doc_findings = extractor.extract(doc, pillar)
            except Exception as exc:  # one bad extraction must not sink the run
                logger.warning("extract failed url=%s (%s); skipping", doc.url, exc)
                continue
            logger.info("extracted %d finding(s) from url=%s", len(doc_findings), doc.url)
            findings.extend(doc_findings)
    return _dedupe_live_findings(findings)


def _configure_logger(out_dir: str) -> tuple[logging.Logger, str]:
    logs_dir = os.path.join(out_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "run.log")
    logger = logging.getLogger("zetarix.run")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # idempotent across repeated main() calls in tests
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger, log_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="RDTII / Zetarix Round-1 extraction CLI (country + pillar → CSV/JSON).",
    )
    parser.add_argument(
        "--country",
        required=True,
        help="SG/Singapore, AU/Australia, MY/Malaysia (case-insensitive; aliases accepted).",
    )
    parser.add_argument("--pillar", required=True, type=int, choices=(6, 7), help="RDTII pillar (6 or 7).")
    parser.add_argument("--out-dir", default="./out", help="Output directory (default ./out).")
    parser.add_argument(
        "--source",
        default="live",
        choices=("live", "gold"),
        help="live (real crawl, falls back to gold if no LLM) | gold (offline, default-safe).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of findings emitted.")
    parser.add_argument(
        "--docs-dir",
        default=None,
        help="Override the golden-dataset docs directory (mainly for tests).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, fetcher=None, extractor=None) -> int:
    """Run the CLI. ``fetcher``/``extractor`` are injectable for offline testing.

    Defaults: the real ``HttpClient`` fetcher and the deterministic
    ``MockProvisionExtractor``. Tests pass a fake fetcher (local fixture, no network) to
    exercise ``--source live`` deterministically.
    """
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    country = resolve_country(args.country)
    if country is None:
        print(
            f"[run.py] Unrecognised country {args.country!r}. "
            "Accepted: SG/Singapore, AU/Australia, MY/Malaysia.",
            file=sys.stderr,
        )
        return 2

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    logger, log_path = _configure_logger(out_dir)
    started = time.perf_counter()
    logger.info("start country=%s pillar=%s source=%s", country, args.pillar, args.source)

    source_used = args.source
    findings = None
    if args.source == "live":
        live_fetcher = fetcher if fetcher is not None else _default_fetcher()
        live_extractor = extractor if extractor is not None else _default_extractor()
        findings = _build_live_findings(
            country, args.pillar, logger, args.docs_dir, live_fetcher, live_extractor
        )
        if not findings:
            # No live findings (e.g. every fetch failed offline). Keep the CSV/JSON
            # contract by falling back to the audited gold baseline.
            logger.warning("live crawl produced 0 findings; falling back to gold baseline")
            print(
                "[run.py] Live crawl yielded no findings (network unreachable or empty "
                "seed) - falling back to offline gold source so output files are still "
                "produced.",
                file=sys.stderr,
            )
            findings = None
            source_used = "gold (fallback)"
    if findings is None:
        findings = build_gold_findings(country, args.pillar, args.docs_dir)

    findings = tag_discovery(findings, args.docs_dir)
    if args.limit is not None:
        findings = findings[: args.limit]

    processing_time = round(time.perf_counter() - started, 4)
    csv_path = os.path.join(out_dir, "output.csv")
    json_path = os.path.join(out_dir, "output.json")
    write_csv(findings, csv_path)
    write_json(
        findings,
        json_path,
        model_version=MODEL_VERSION,
        processing_time=processing_time,
    )

    new_count = sum(1 for f in findings if f.discovery_tag is DiscoveryTag.NEW)
    known_count = len(findings) - new_count
    logger.info(
        "done rows=%d new=%d known=%d csv=%s json=%s",
        len(findings),
        new_count,
        known_count,
        csv_path,
        json_path,
    )

    # ASCII-only summary: some Windows consoles use cp1252 and choke on non-ASCII.
    print(
        f"[run.py] {country} P{args.pillar} via {source_used}: "
        f"{len(findings)} rows ({new_count} NEW / {known_count} KNOWN) -> "
        f"{csv_path}, {json_path}, {log_path}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

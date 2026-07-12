"""Shared extraction pipeline service for API and future workflow workers.

This module is the production-facing orchestration boundary. It keeps HTTP adapters from
importing the CLI script while preserving the current reviewer-contract behavior:
offline gold mode, live crawl with deterministic fallback, discovery tagging, and
bounded output rows.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Literal

from zetarix.cleaning.dom_cleaner import DomCleaner
from zetarix.domain.document import CrawledDocument
from zetarix.domain.entities import DiscoveryTag, Finding, Pillar
from zetarix.domain.indicator_codes import to_canonical
from zetarix.scoring.golden_dataset import GoldRecord, load_gold_records, load_reference_items
from zetarix.scoring.scoring import discovery_diff, finding_to_match_item
from zetarix.transport.http_client import HttpClient
from zetarix.transport.pdf_parser import PdfParser

SourceMode = Literal["gold", "live"]

MODEL_VERSION = "zetarix-round1-gold-1.0"

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


@dataclass(frozen=True)
class PipelineRequest:
    country: str
    pillar: int
    source: SourceMode = "gold"
    limit: int | None = None
    docs_dir: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    country: str
    pillar: int
    source: str
    findings: list[Finding]
    processing_time: float


def resolve_country(raw: str) -> str | None:
    if not raw:
        return None
    return _COUNTRY_ALIASES.get(raw.strip().lower())


def last_amended_year(timeframe: str) -> date | None:
    years = [int(match.group()) for match in _YEAR_RE.finditer(timeframe or "")]
    if not years:
        return None
    return date(max(years), 1, 1)


def gold_record_to_finding(record: GoldRecord) -> Finding:
    pillar = Pillar(record.pillar_id)
    return Finding(
        title=record.act_name,
        last_update=last_amended_year(record.timeframe),
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
    records = load_gold_records(docs_dir) if docs_dir else load_gold_records()
    return [
        gold_record_to_finding(record)
        for record in records
        if record.country == country and record.pillar_id == pillar
    ]


def tag_discovery(findings: list[Finding], docs_dir: str | None = None) -> list[Finding]:
    gold = list(load_gold_records(docs_dir) if docs_dir else load_gold_records())
    references = load_reference_items(docs_dir) if docs_dir else load_reference_items()
    novel_items = discovery_diff(findings, gold, references)
    novel_keys = {(item.act_name, item.indicator_id) for item in novel_items}

    tagged: list[Finding] = []
    for finding in findings:
        item = finding_to_match_item(finding)
        tag = DiscoveryTag.NEW if (item.act_name, item.indicator_id) in novel_keys else DiscoveryTag.KNOWN
        tagged.append(replace(finding, discovery_tag=tag))
    return tagged


def default_extractor():
    grounding = os.environ.get("ZETARIX_GROUNDING", "few_shot")
    os.environ.setdefault("ZETARIX_LLM_BACKEND", "local")
    splits_default = Path(__file__).resolve().parents[3] / "data" / "training" / "splits"
    os.environ.setdefault("ZETARIX_TRAINING_SPLITS", str(splits_default))
    if grounding == "few_shot" and llm_backend_available():
        try:
            from zetarix.extraction.llm_provision_extractor import LLMProvisionExtractor
            from zetarix.inference.grounding import load_retriever
            from zetarix.llm.router import LLMRouter

            if load_retriever() is not None:
                return LLMProvisionExtractor(LLMRouter.from_env())
        except Exception as exc:
            logging.getLogger("zetarix.pipeline").warning(
                "LLMProvisionExtractor unavailable (%s); falling back to mock", exc
            )

    from zetarix.extraction.mock_provision_extractor import MockProvisionExtractor

    return MockProvisionExtractor()


def llm_backend_available() -> bool:
    backend = os.environ.get("ZETARIX_LLM_BACKEND", "local").lower()
    if backend == "remote":
        return bool(
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("CLAUDE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    if backend not in {"local", "hybrid"}:
        return False

    endpoint = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def default_fetcher():
    return HttpClient()


def seed_urls(country: str, pillar: int, docs_dir: str | None = None) -> list[str]:
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


def crawl_one(url: str, country: str, fetcher, logger: logging.Logger) -> CrawledDocument | None:
    try:
        result = fetcher.fetch_raw(url)
    except Exception as exc:
        logger.warning("fetch failed url=%s (%s); skipping", url, exc)
        return None

    try:
        if result.is_pdf:
            text = PdfParser().extract_text(result.body)
            return CrawledDocument(url=url, economy=country, text=text, is_pdf=True)

        text = DomCleaner().clean_html(result.text)
        return CrawledDocument(url=url, economy=country, text=text, is_pdf=False)
    except Exception as exc:
        logger.warning("parse failed url=%s (%s); skipping", url, exc)
        return None


def build_live_findings(
    country: str,
    pillar: int,
    logger: logging.Logger,
    docs_dir: str | None = None,
    fetcher=None,
    extractor=None,
) -> list[Finding]:
    live_fetcher = fetcher if fetcher is not None else default_fetcher()
    live_extractor = extractor if extractor is not None else default_extractor()
    seed = seed_urls(country, pillar, docs_dir)
    logger.info("live crawl seeded with %d url(s)", len(seed))

    findings: list[Finding] = []
    for url in seed:
        doc = crawl_one(url, country, live_fetcher, logger)
        if doc is None:
            continue
        try:
            doc_findings = live_extractor.extract(doc, pillar)
        except Exception as exc:
            logger.warning("extract failed url=%s (%s); skipping", url, exc)
            continue
        logger.info("extracted %d finding(s) from url=%s", len(doc_findings), url)
        findings.extend(doc_findings)
    return findings


def configure_logger(out_dir: str) -> tuple[logging.Logger, str]:
    logs_dir = os.path.join(out_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "run.log")
    logger = logging.getLogger("zetarix.pipeline")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger, log_path


def run_pipeline(
    request: PipelineRequest,
    *,
    logger: logging.Logger | None = None,
    fetcher=None,
    extractor=None,
) -> PipelineResult:
    started = time.perf_counter()
    country = resolve_country(request.country)
    if country is None:
        raise ValueError("Unrecognised country. Accepted: SG/Singapore, AU/Australia, MY/Malaysia.")
    if request.pillar not in {6, 7}:
        raise ValueError("pillar must be 6 or 7")

    source_used = request.source
    findings: list[Finding] | None = None
    if request.source == "live":
        if logger is None:
            with tempfile.TemporaryDirectory(prefix="zetarix-pipeline-") as out_dir:
                temp_logger, _ = configure_logger(out_dir)
                findings = build_live_findings(
                    country, request.pillar, temp_logger, request.docs_dir, fetcher, extractor
                )
        else:
            findings = build_live_findings(
                country, request.pillar, logger, request.docs_dir, fetcher, extractor
            )
        if not findings:
            findings = None
            source_used = "gold (fallback)"

    if findings is None:
        findings = build_gold_findings(country, request.pillar, request.docs_dir)

    findings = tag_discovery(findings, request.docs_dir)
    if request.limit is not None:
        findings = findings[: request.limit]

    return PipelineResult(
        country=country,
        pillar=request.pillar,
        source=source_used,
        findings=findings,
        processing_time=round(time.perf_counter() - started, 4),
    )

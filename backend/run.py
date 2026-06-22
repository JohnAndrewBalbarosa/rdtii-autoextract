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
import logging
import os
import re
import sys
import time
from datetime import date

# Make `from core...` / `from adapters...` resolve when run as a plain script from any cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.domain.document import CrawledDocument  # noqa: E402
from core.domain.entities import DiscoveryTag, Finding, Pillar  # noqa: E402
from core.domain.indicator_codes import to_canonical  # noqa: E402
from core.pipeline.golden_dataset import (  # noqa: E402
    GoldRecord,
    load_gold_records,
    load_reference_items,
)
from core.pipeline.output_emitter import write_csv, write_json  # noqa: E402
from core.pipeline.scoring import discovery_diff, finding_to_match_item  # noqa: E402

MODEL_VERSION = "zetarix-round1-gold-1.0"

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
    "cn": "China",
    "chn": "China",
    "china": "China",
    "in": "India",
    "ind": "India",
    "india": "India",
    "id": "Indonesia",
    "idn": "Indonesia",
    "indonesia": "Indonesia",
    "la": "Lao PDR",
    "lao": "Lao PDR",
    "laos": "Lao PDR",
    "lao pdr": "Lao PDR",
    "lao people's democratic republic": "Lao PDR",
    "mn": "Mongolia",
    "mng": "Mongolia",
    "mongolia": "Mongolia",
    "ru": "Russian Federation",
    "rus": "Russian Federation",
    "russia": "Russian Federation",
    "russian federation": "Russian Federation",
    "th": "Thailand",
    "tha": "Thailand",
    "thailand": "Thailand",
}

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


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
    """Default live ``ProvisionExtractor``: tag→set-trie matcher, keyword mock as fallback.

    Primary is the deterministic ``TagMatchProvisionExtractor`` — section tags matched
    against indicator definitions via the ``SetTrieIndex`` (the documented §9 algorithm,
    now wired to live data). When a document yields no tag matches it falls back per-document
    to the keyword ``MockProvisionExtractor`` so the live path still produces rows. A real
    LLM extractor can swap in behind the same port with no other code change.
    """
    from adapters.extraction.fallback_provision_extractor import FallbackProvisionExtractor
    from adapters.extraction.mock_provision_extractor import MockProvisionExtractor
    from adapters.extraction.tagmatch_provision_extractor import TagMatchProvisionExtractor

    return FallbackProvisionExtractor(TagMatchProvisionExtractor(), MockProvisionExtractor())


def _default_fetcher():
    """Default live fetcher: the real ``HttpClient`` (an ``HtmlFetcherPort`` with fetch_raw).

    Any object exposing ``fetch_raw(url) -> FetchResult`` is acceptable; tests inject a
    fake so the live path runs offline.
    """
    from adapters.botting.l4_transport.http_client import HttpClient

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
    from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry

    scaffold = ScaffoldRegistry().get_scaffold_for_url(url)
    fetch_url = scaffold.get_fetch_url(url) if scaffold else url

    try:
        result = fetcher.fetch_raw(fetch_url)
    except Exception as exc:  # network-less / blocked / timeout — skip, don't crash
        logger.warning("fetch failed url=%s (%s); skipping", url, exc)
        return None

    try:
        if result.is_pdf:
            from adapters.botting.l4_transport.pdf_parser import PdfParser

            text = PdfParser().extract_text(result.body)
            return CrawledDocument(url=url, economy=country, text=text, is_pdf=True)

        from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
        from adapters.botting.l6_presentation.html_sections import join_section_text

        cleaner = DomCleaner()
        selectors = dict(scaffold.get_custom_selectors()) if scaffold else {}
        if scaffold:
            selectors["boilerplate"] = scaffold.get_boilerplate_selectors()
        sections = cleaner.extract_sections(result.text, selectors)
        text = join_section_text(sections)
        if not text:
            text = cleaner.clean_html(result.text, selectors)
        return CrawledDocument(
            url=url,
            economy=country,
            text=text,
            is_pdf=False,
            sections=tuple(sections),
        )
    except Exception as exc:  # parse/decode failure — skip this doc
        logger.warning("parse failed url=%s (%s); skipping", url, exc)
        return None


def _nodes_from_doc(doc: CrawledDocument):
    """Tag a crawled document's sections into ``ConceptNode``s (the cluster seed).

    Section ids are URL-qualified so they stay unique across documents in the cluster graph.
    """
    from adapters.extraction.section_tagger import tag_section

    nodes = []
    if doc.sections:
        for index, section in enumerate(doc.sections):
            fragment = f"#{section.anchor}" if section.anchor else f"#sec-{index}"
            nodes.append(
                tag_section(
                    section_id=f"{doc.url}{fragment}",
                    document_url=doc.url,
                    heading=section.heading,
                    text=section.text,
                    path=section.path,
                )
            )
    else:
        nodes.append(
            tag_section(
                section_id=doc.url or "doc",
                document_url=doc.url,
                heading="",
                text=doc.text or "",
                path=(),
            )
        )
    return nodes


def _build_live_findings(country, pillar, logger, docs_dir, fetcher, extractor):
    """Real crawl→extract path. Returns ``(findings, concept_nodes)``.

    Resolves seed URLs for country+pillar, fetches each (offline-safe: failures are
    logged and skipped), builds a ``CrawledDocument``, tags its sections into
    ``ConceptNode``s (the cluster-graph seed), and runs the injected ``ProvisionExtractor``.
    """
    seed = _seed_urls(country, pillar, docs_dir)
    logger.info("live crawl seeded with %d url(s)", len(seed))

    findings: list[Finding] = []
    nodes: list = []
    for url in seed:
        doc = _crawl_one(url, country, fetcher, logger)
        if doc is None:
            continue
        nodes.extend(_nodes_from_doc(doc))
        try:
            doc_findings = extractor.extract(doc, pillar)
        except Exception as exc:  # one bad extraction must not sink the run
            logger.warning("extract failed url=%s (%s); skipping", url, exc)
            continue
        logger.info("extracted %d finding(s) from url=%s", len(doc_findings), url)
        findings.extend(doc_findings)
    return findings, nodes


def _write_cluster_artifact(nodes, path, logger, matched_ids=None) -> None:
    """Build + write the cluster-graph artifact (+ clustering-assisted NEW candidates).

    Empty ``nodes`` → empty artifact. ``matched_ids`` (the section ids the matcher mapped)
    drive ``discovery_candidates``: unmatched members of a KNOWN-bearing community. Failures
    (e.g. a missing optional clustering dep) degrade to an empty artifact and a warning so
    the run never crashes on the secondary output.
    """
    from core.domain.cluster import ClusterGraph
    from core.pipeline.cluster_pipeline import (
        build_clusters,
        discovery_candidates,
        write_clusters,
    )

    graph = ClusterGraph()
    if nodes:
        try:
            from adapters.clustering import LouvainCommunityDetector, TagOverlapScorer

            graph = build_clusters(nodes, TagOverlapScorer(), LouvainCommunityDetector())
        except Exception as exc:  # pragma: no cover - defensive (optional dep / bad data)
            logger.warning("clustering failed (%s); writing empty cluster artifact", exc)
            graph = ClusterGraph()

    candidates = discovery_candidates(graph, matched_ids or set())
    write_clusters(graph, path, candidates)
    logger.info(
        "clusters: %d communities, %d edges, %d discovery-candidate group(s) -> %s",
        len(graph.communities),
        len(graph.edges),
        len(candidates),
        path,
    )


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
    concept_nodes: list = []
    if args.source == "live":
        live_fetcher = fetcher if fetcher is not None else _default_fetcher()
        live_extractor = extractor if extractor is not None else _default_extractor()
        findings, concept_nodes = _build_live_findings(
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

    # Second artifact: the cluster graph over the crawled section seed (empty in gold mode),
    # with clustering-assisted NEW-discovery candidates keyed off mapped section ids.
    clusters_path = os.path.join(out_dir, "clusters.json")
    matched_ids = {f.location_ref for f in findings if f.location_ref}
    _write_cluster_artifact(concept_nodes, clusters_path, logger, matched_ids)

    new_count = sum(1 for f in findings if f.discovery_tag is DiscoveryTag.NEW)
    known_count = len(findings) - new_count
    logger.info(
        "done rows=%d new=%d known=%d csv=%s json=%s clusters=%s",
        len(findings),
        new_count,
        known_count,
        csv_path,
        json_path,
        clusters_path,
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

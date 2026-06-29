"""Round-1 output emitter — ``Finding`` → submission CSV (p.14) + JSON (p.15).

The CSV is the *primary* deliverable; its column order and names are the official
Round-1 contract (``docs/ROUND1_SUBMISSION_SPEC.md`` p.14) and MUST NOT drift. The JSON
is the supplementary envelope grouping findings by law, with the per-provision audit
fields a human reviewer needs.

Pure and serializable: no web/LLM/storage imports, no mutation of inputs. ``csv`` and
``json`` are stdlib. This module only *formats* — discovery tagging, scraping, and
extraction happen upstream.
"""

from __future__ import annotations

import csv
import json
from collections import OrderedDict
from dataclasses import dataclass

from core.domain.entities import Finding

# The exact p.14 column order. This tuple is the contract — tests assert it verbatim.
CSV_COLUMNS: tuple[str, ...] = (
    "Economy",
    "Law Name",
    "Law Number / Ref",
    "Last Amended",
    "Indicator ID",
    "Article / Section",
    "Discovery Tag",
    "Location Reference",
    "Verbatim Snippet",
    "Mapping Rationale",
    "Source URL",
    "Confidence",
    "Notes",
)


def _clean_field(val: str | None) -> str:
    if not val:
        return ""
    # Collapse any form of newlines or carriage returns into a single space
    cleaned = val.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    import re
    return re.sub(r"\s+", " ", cleaned).strip()


def _format_url(val: str | None) -> str:
    if not val:
        return ""
    cleaned = _clean_field(val)
    if cleaned.startswith(("http://", "https://", "www.")):
        url = cleaned
        if cleaned.startswith("www."):
            url = "https://" + cleaned
        return f'=HYPERLINK("{url}")'
    return cleaned


def _last_amended(finding: Finding) -> str:
    """``Last Amended`` is the amendment *year* as a string; blank when unknown."""
    if finding.last_update is None:
        return ""
    return str(finding.last_update.year)


def _row_dict(finding: Finding) -> "OrderedDict[str, str]":
    """One CSV row as an ordered dict keyed by the p.14 column names."""
    return OrderedDict(
        (
            ("Economy", _clean_field(finding.economy)),
            ("Law Name", _clean_field(finding.title)),
            ("Law Number / Ref", _clean_field(finding.law_number)),
            ("Last Amended", _last_amended(finding)),
            ("Indicator ID", _clean_field(finding.indicator)),
            ("Article / Section", _clean_field(finding.article_section)),
            ("Discovery Tag", finding.discovery_tag.value),
            ("Location Reference", _format_url(finding.location_ref)),
            ("Verbatim Snippet", _clean_field(finding.verbatim_snippet)),
            ("Mapping Rationale", _clean_field(finding.mapping_rationale)),
            ("Source URL", _format_url(finding.url)),
            ("Confidence", f"{finding.confidence:.2f}"),
            ("Notes", _clean_field(finding.notes)),
        )
    )


def findings_to_csv_dicts(findings: list[Finding]) -> list[dict]:
    """Return the list of row dicts (column name → string) for ``findings``.

    Exposed for testing and for any caller that wants the rows without writing a file.
    """
    return [dict(_row_dict(finding)) for finding in findings]


def write_csv(findings: list[Finding], path) -> None:
    """Write ``findings`` to ``path`` as the p.14 CSV (header always present).

    Empty ``findings`` still writes the header row (header-only file), so the output
    contract holds even when nothing was extracted.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for finding in findings:
            writer.writerow(_row_dict(finding))


def _provision_obj(finding: Finding) -> "OrderedDict[str, object]":
    """The per-provision audit object inside a law's ``provisions[]`` array (p.15)."""
    # raw_context = surrounding text for human review. We have no dedicated field, so
    # fall back to the longer of provisions/notes when present (empty string is fine).
    raw_context = finding.provisions or finding.notes or ""
    return OrderedDict(
        (
            ("indicator_id", finding.indicator),
            ("article", finding.article_section),
            ("verbatim", finding.verbatim_snippet),
            ("mapping_rationale", finding.mapping_rationale),
            ("discovery_tag", finding.discovery_tag.value),
            ("source_url", finding.url),
            ("confidence", round(finding.confidence, 2)),
            ("raw_context", raw_context),
        )
    )


@dataclass(frozen=True)
class _LawKey:
    economy: str
    law_name: str


def findings_to_json_objects(
    findings: list[Finding],
    *,
    model_version: str = "",
    ocr_quality_cer=None,
    processing_time=None,
    source_pdf_path_by_law: dict | None = None,
) -> list[dict]:
    """Group ``findings`` into the p.15 law objects (the JSON envelope payload).

    One object per ``(economy, law_name)`` pair, insertion-ordered, each carrying the
    metadata fields and a ``provisions[]`` array. Returns a plain serializable list.
    """
    pdf_paths = source_pdf_path_by_law or {}
    grouped: "OrderedDict[_LawKey, list[Finding]]" = OrderedDict()
    for finding in findings:
        key = _LawKey(economy=finding.economy, law_name=finding.title)
        grouped.setdefault(key, []).append(finding)

    laws: list[dict] = []
    for key, group in grouped.items():
        source_pdf_path = (
            pdf_paths.get((key.economy, key.law_name))
            or pdf_paths.get(key.law_name)
        )
        law = OrderedDict(
            (
                ("economy", key.economy),
                ("law_name", key.law_name),
                ("source_pdf_path", source_pdf_path),
                ("ocr_quality_cer", ocr_quality_cer),
                ("processing_time", processing_time),
                ("model_version", model_version),
                ("provisions", [dict(_provision_obj(f)) for f in group]),
            )
        )
        laws.append(dict(law))
    return laws


def write_json(
    findings: list[Finding],
    path,
    *,
    model_version: str = "",
    ocr_quality_cer=None,
    processing_time=None,
    source_pdf_path_by_law: dict | None = None,
) -> None:
    """Write the p.15 JSON envelope (a list of law objects) to ``path``.

    Empty ``findings`` writes ``[]``. UTF-8, pretty-printed, non-ASCII preserved so
    bilingual statute names survive round-trips.
    """
    laws = findings_to_json_objects(
        findings,
        model_version=model_version,
        ocr_quality_cer=ocr_quality_cer,
        processing_time=processing_time,
        source_pdf_path_by_law=source_pdf_path_by_law,
    )
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(laws, handle, ensure_ascii=False, indent=2)

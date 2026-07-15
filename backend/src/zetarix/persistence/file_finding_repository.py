"""File-backed FindingRepository for the review MVP.

Stores the current findings set, review state, and run metadata as JSON on disk so the
frontend review console can persist changes without introducing a new database layer.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha1
from threading import Lock
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from zetarix.domain.entities import DiscoveryTag, Finding, Pillar, ReviewStatus
from zetarix.ports import FindingRepository


def _today_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding_id(finding: Finding) -> str:
    key = "|".join(
        [
            finding.economy,
            finding.title,
            finding.indicator,
            finding.article_section,
            finding.url,
        ]
    )
    return sha1(key.encode("utf-8")).hexdigest()[:16]


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url or ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "ref", "source"}]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(sorted(query)), ""))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def _dedupe_key(finding: Finding) -> tuple[str, str, str, str]:
    return (
        _canonical_url(finding.url) or _normalize_text(finding.title),
        _normalize_text(finding.title),
        _normalize_text(finding.article_section),
        finding.indicator,
    )


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    best: dict[tuple[str, str, str, str], Finding] = {}
    for finding in findings:
        key = _dedupe_key(finding)
        current = best.get(key)
        if current is None:
            best[key] = finding
            continue
        current_score = (current.confidence, len(current.verbatim_snippet), len(current.provisions))
        candidate_score = (finding.confidence, len(finding.verbatim_snippet), len(finding.provisions))
        if candidate_score > current_score:
            best[key] = finding
    return list(best.values())


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _serialize_finding(finding: Finding) -> dict[str, Any]:
    canonical_url = _canonical_url(finding.url)
    return {
        "title": finding.title,
        "last_update": finding.last_update.isoformat() if finding.last_update else None,
        "url": canonical_url,
        "scope": finding.scope,
        "provisions": finding.provisions,
        "impact": finding.impact,
        "pillar": finding.pillar.value,
        "indicator": finding.indicator,
        "confidence": finding.confidence,
        "review_status": finding.review_status.value,
        "economy": finding.economy,
        "law_number": finding.law_number,
        "article_section": finding.article_section,
        "discovery_tag": finding.discovery_tag.value,
        "verbatim_snippet": finding.verbatim_snippet,
        "mapping_rationale": finding.mapping_rationale,
        "location_ref": _canonical_url(finding.location_ref or "") or finding.location_ref,
        "notes": finding.notes,
    }


def _deserialize_finding(payload: dict[str, Any]) -> Finding:
    return Finding(
        title=payload["title"],
        last_update=_parse_date(payload.get("last_update")),
        url=payload.get("url", ""),
        scope=payload.get("scope", ""),
        provisions=payload.get("provisions", ""),
        impact=payload.get("impact", ""),
        pillar=Pillar(payload["pillar"]),
        indicator=payload.get("indicator", ""),
        confidence=float(payload.get("confidence", 0.0)),
        review_status=ReviewStatus(payload.get("review_status", ReviewStatus.PENDING.value)),
        economy=payload.get("economy", ""),
        law_number=payload.get("law_number"),
        article_section=payload.get("article_section", ""),
        discovery_tag=DiscoveryTag(payload.get("discovery_tag", DiscoveryTag.KNOWN.value)),
        verbatim_snippet=payload.get("verbatim_snippet", ""),
        mapping_rationale=payload.get("mapping_rationale", ""),
        location_ref=payload.get("location_ref"),
        notes=payload.get("notes", ""),
    )


def _default_record(finding: Finding) -> dict[str, Any]:
    return {
        "id": _finding_id(finding),
        "finding": _serialize_finding(finding),
        "language": "en",
        "indicator_label": finding.indicator,
        "document_title": finding.title,
        "article_number": finding.article_section,
        "created_at": _today_iso(),
        "updated_at": _today_iso(),
    }


class FileFindingRepository(FindingRepository):
    """Minimal JSON-backed repository for MVP persistence."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self._write({"version": 1, "metadata": {}, "findings": []})

    def save(self, finding: Finding) -> None:
        with self._lock:
            data = self._read()
            record = _default_record(finding)
            existing = self._find_index(data, record["id"])
            if existing >= 0:
                data["findings"][existing] = record
            else:
                data["findings"].append(record)
            self._write(data)

    def replace_all(self, findings: list[Finding], metadata: dict | None = None) -> None:
        with self._lock:
            data = self._read()
            existing = {item["id"]: item for item in data.get("findings", [])}
            new_records: list[dict[str, Any]] = []
            for finding in _dedupe_findings(findings):
                record = _default_record(finding)
                prev = existing.get(record["id"])
                if prev:
                    prev_finding = prev.get("finding", {})
                    record["finding"]["review_status"] = prev_finding.get(
                        "review_status",
                        record["finding"]["review_status"],
                    )
                    for key in (
                        "scope",
                        "provisions",
                        "impact",
                        "notes",
                        "article_section",
                        "title",
                    ):
                        if prev_finding.get(key):
                            record["finding"][key] = prev_finding[key]
                    record["language"] = prev.get("language", record["language"])
                    record["indicator_label"] = prev.get("indicator_label", record["indicator_label"])
                    record["document_title"] = prev.get("document_title", record["document_title"])
                    record["article_number"] = prev.get("article_number", record["article_number"])
                    record["created_at"] = prev.get("created_at", record["created_at"])
                new_records.append(record)
            self._write(
                {
                    "version": 1,
                    "metadata": metadata or {},
                    "findings": new_records,
                }
            )

    def list_all(self) -> list[Finding]:
        with self._lock:
            return [_deserialize_finding(item["finding"]) for item in self._read().get("findings", [])]

    def get(self, finding_id: str) -> Finding | None:
        with self._lock:
            data = self._read()
            idx = self._find_index(data, finding_id)
            if idx < 0:
                return None
            return _deserialize_finding(data["findings"][idx]["finding"])

    def get_record(self, finding_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            idx = self._find_index(data, finding_id)
            if idx < 0:
                return None
            return dict(data["findings"][idx])

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._read().get("findings", [])]

    def update(self, finding_id: str, changes: dict) -> Finding | None:
        with self._lock:
            data = self._read()
            idx = self._find_index(data, finding_id)
            if idx < 0:
                return None
            record = data["findings"][idx]
            payload = dict(record["finding"])

            field_map = {
                "title": "title",
                "scope": "scope",
                "provisions": "provisions",
                "impact": "impact",
                "review_status": "review_status",
                "article_section": "article_section",
                "notes": "notes",
                "verbatim_snippet": "verbatim_snippet",
                "mapping_rationale": "mapping_rationale",
                "location_ref": "location_ref",
                "confidence": "confidence",
            }
            for key, target in field_map.items():
                if key in changes and changes[key] is not None:
                    payload[target] = changes[key]

            if "language" in changes and changes["language"]:
                record["language"] = changes["language"]
            if "indicator_label" in changes and changes["indicator_label"]:
                record["indicator_label"] = changes["indicator_label"]
            if "document_title" in changes and changes["document_title"]:
                record["document_title"] = changes["document_title"]
            if "article_number" in changes and changes["article_number"] is not None:
                record["article_number"] = changes["article_number"]
                payload["article_section"] = changes["article_number"]

            finding = _deserialize_finding(payload)
            record["finding"] = _serialize_finding(finding)
            record["document_title"] = changes.get("document_title", record.get("document_title", finding.title))
            record["article_number"] = changes.get("article_number", record.get("article_number", finding.article_section))
            record["updated_at"] = _today_iso()
            data["findings"][idx] = record
            self._write(data)
            return finding

    def list_pending(self) -> list[Finding]:
        return [item for item in self.list_all() if item.review_status is ReviewStatus.PENDING]

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._read().get("metadata", {}))

    def statistics(self) -> dict[str, Any]:
        records = self.list_records()
        total = len(records)
        pending = 0
        verified = 0
        rejected = 0
        by_pillar: dict[int, int] = {}
        for item in records:
            finding = item["finding"]
            status = finding.get("review_status", ReviewStatus.PENDING.value)
            if status == ReviewStatus.VERIFIED.value:
                verified += 1
            elif status == ReviewStatus.REJECTED.value:
                rejected += 1
            else:
                pending += 1
            pillar = int(finding["pillar"])
            by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
        reviewed = verified + rejected
        return {
            "total": total,
            "pending": pending,
            "verified": verified,
            "rejected": rejected,
            "reviewed": reviewed,
            "progress": round((reviewed / total) * 100) if total else 0,
            "by_pillar": by_pillar,
            "metadata": self.metadata(),
        }

    def finding_id(self, finding: Finding) -> str:
        return _finding_id(finding)

    @staticmethod
    def _find_index(data: dict[str, Any], finding_id: str) -> int:
        for i, item in enumerate(data.get("findings", [])):
            if item.get("id") == finding_id:
                return i
        return -1

    def _read(self) -> dict[str, Any]:
        with open(self._path, encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, data: dict[str, Any]) -> None:
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

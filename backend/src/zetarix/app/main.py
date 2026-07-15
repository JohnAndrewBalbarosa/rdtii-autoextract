"""FastAPI reference backend for the MVP review workflow.

The adapter stays thin: it maps HTTP onto the existing pipeline, persistence, and
output contracts without moving domain logic into the web layer.
"""

from __future__ import annotations

import csv
import io
import importlib.util
import logging
import os
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from zetarix.domain.entities import Finding
from zetarix.domain.indicator_codes import pillar_of
from zetarix.orchestration.output_emitter import CSV_COLUMNS, findings_to_csv_dicts, findings_to_json_objects
from zetarix.persistence.file_finding_repository import FileFindingRepository

app = FastAPI(
    title="RDTII Trade Regulatory Analysis Engine",
    version="0.1.0",
    description="Automates ~80% of the ESCAP RDTII workflow: search -> retrieve -> describe.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PipelineRunRequest(BaseModel):
    country: str = Field(..., examples=["SG"])
    pillar: Literal[6, 7]
    source: Literal["live", "gold"] = "live"
    limit: int | None = None
    docs_dir: str | None = None


class FindingResponse(BaseModel):
    id: str
    title: str
    lastUpdate: str | None
    url: str
    scope: str
    provisions: str
    impact: str
    pillar: Literal[6, 7]
    indicator: str
    indicatorLabel: str
    confidence: float
    reviewStatus: Literal["pending", "verified", "rejected"]
    jurisdiction: str
    documentTitle: str
    articleNumber: str
    language: str
    discoveryTag: str
    verbatimSnippet: str
    mappingRationale: str
    locationRef: str | None
    notes: str


class FindingPatchRequest(BaseModel):
    title: str | None = None
    scope: str | None = None
    provisions: str | None = None
    impact: str | None = None
    reviewStatus: Literal["pending", "verified", "rejected"] | None = None
    articleNumber: str | None = None
    language: str | None = None
    indicatorLabel: str | None = None
    notes: str | None = None
    verbatimSnippet: str | None = None
    mappingRationale: str | None = None
    locationRef: str | None = None
    confidence: float | None = None


class ReviewRequest(BaseModel):
    findingId: str
    status: Literal["pending", "verified", "rejected"]
    notes: str | None = None


def _backend_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@lru_cache(maxsize=1)
def _cli_run_module():
    backend_root = _backend_root()
    run_path = os.path.join(backend_root, "run.py")
    spec = importlib.util.spec_from_file_location("zetarix_backend_run", run_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load backend run module from {run_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _repository() -> FileFindingRepository:
    path = os.environ.get("ZETARIX_FINDINGS_PATH")
    if not path:
        path = os.path.join(_backend_root(), "out", "findings_store.json")
    return FileFindingRepository(path)


def _indicator_label(indicator: str) -> str:
    labels = {
        "P6-I1": "Restriction on cross-border transfer",
        "P6-I2": "Data localisation / residency requirement",
        "P6-I3": "Transfer impact / assessment requirement",
        "P7-I1": "Security obligations",
        "P7-I2": "Accountability of controller",
        "P7-I3": "Data subject rights",
        "P7-I4": "Personal data processing obligations",
        "P7-I5": "Processing conditions",
    }
    return labels.get(indicator, indicator)


def _finding_to_response(record: dict) -> FindingResponse:
    finding = record["finding"]
    pillar = int(finding["pillar"])
    return FindingResponse(
        id=record["id"],
        title=finding["title"],
        lastUpdate=finding.get("last_update"),
        url=finding.get("url", ""),
        scope=finding.get("scope", ""),
        provisions=finding.get("provisions", ""),
        impact=finding.get("impact", ""),
        pillar=pillar,
        indicator=finding.get("indicator", ""),
        indicatorLabel=record.get("indicator_label") or _indicator_label(finding.get("indicator", "")),
        confidence=float(finding.get("confidence", 0.0)),
        reviewStatus=finding.get("review_status", "pending"),
        jurisdiction=finding.get("economy", ""),
        documentTitle=record.get("document_title") or finding.get("title", ""),
        articleNumber=record.get("article_number") or finding.get("article_section", ""),
        language=record.get("language", "en"),
        discoveryTag=finding.get("discovery_tag", "KNOWN"),
        verbatimSnippet=finding.get("verbatim_snippet", ""),
        mappingRationale=finding.get("mapping_rationale", ""),
        locationRef=finding.get("location_ref"),
        notes=finding.get("notes", ""),
    )


def _run_pipeline(request: PipelineRunRequest) -> tuple[list[Finding], dict]:
    cli_run = _cli_run_module()

    country = cli_run.resolve_country(request.country)
    if country is None:
        raise HTTPException(status_code=400, detail="Unsupported country. Use SG, AU, or MY.")

    logger = logging.getLogger("zetarix.api.pipeline")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    findings: list[Finding] | None = None
    source_used = request.source
    if request.source == "live":
        findings = cli_run._build_live_findings(
            country,
            request.pillar,
            logger,
            request.docs_dir,
            cli_run._default_fetcher(),
            cli_run._default_extractor(),
        )
        if not findings:
            findings = None
            source_used = "gold (fallback)"
    if findings is None:
        findings = cli_run.build_gold_findings(country, request.pillar, request.docs_dir)

    findings = cli_run.tag_discovery(findings, request.docs_dir)
    if request.limit is not None:
        findings = findings[: request.limit]

    metadata = {
        "country": country,
        "pillar": request.pillar,
        "source_requested": request.source,
        "source_used": source_used,
        "row_count": len(findings),
    }
    return findings, metadata


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for self-hosted deployments (R16)."""
    return {"status": "ok"}


@app.get("/findings", response_model=list[FindingResponse])
def list_findings() -> list[FindingResponse]:
    return [_finding_to_response(item) for item in _repository().list_records()]


@app.get("/findings/{finding_id}", response_model=FindingResponse)
def get_finding(finding_id: str) -> FindingResponse:
    record = _repository().get_record(finding_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _finding_to_response(record)


@app.patch("/findings/{finding_id}", response_model=FindingResponse)
def patch_finding(finding_id: str, payload: FindingPatchRequest) -> FindingResponse:
    changes = payload.model_dump(exclude_none=True)
    if "reviewStatus" in changes:
        changes["review_status"] = changes.pop("reviewStatus")
    if "articleNumber" in changes:
        changes["article_number"] = changes.pop("articleNumber")
    if "indicatorLabel" in changes:
        changes["indicator_label"] = changes.pop("indicatorLabel")
    if "verbatimSnippet" in changes:
        changes["verbatim_snippet"] = changes.pop("verbatimSnippet")
    if "mappingRationale" in changes:
        changes["mapping_rationale"] = changes.pop("mappingRationale")
    if "locationRef" in changes:
        changes["location_ref"] = changes.pop("locationRef")

    finding = _repository().update(finding_id, changes)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    record = _repository().get_record(finding_id)
    assert record is not None
    return _finding_to_response(record)


@app.post("/review", response_model=FindingResponse)
def review_finding(payload: ReviewRequest) -> FindingResponse:
    changes = {"review_status": payload.status}
    if payload.notes:
        changes["notes"] = payload.notes
    finding = _repository().update(payload.findingId, changes)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    record = _repository().get_record(payload.findingId)
    assert record is not None
    return _finding_to_response(record)


@app.get("/statistics")
def statistics() -> dict:
    return _repository().statistics()


@app.get("/export")
def export_findings(format: Literal["csv", "json"] = "json"):
    repo = _repository()
    findings = repo.list_all()
    metadata = repo.metadata()
    if format == "json":
        payload = findings_to_json_objects(
            findings,
            model_version=str(metadata.get("source_used", "")),
            processing_time=None,
        )
        return JSONResponse(payload)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in findings_to_csv_dicts(findings):
        writer.writerow(row)
    filename = "findings_export.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/pipeline/run")
def run_pipeline(request: PipelineRunRequest) -> dict:
    findings, metadata = _run_pipeline(request)
    _repository().replace_all(findings, metadata=metadata)
    return {
        "stored": len(findings),
        "metadata": metadata,
        "statistics": _repository().statistics(),
        "findings": [_finding_to_response(item).model_dump() for item in _repository().list_records()],
    }

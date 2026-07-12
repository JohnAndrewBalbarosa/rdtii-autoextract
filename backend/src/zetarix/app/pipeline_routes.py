"""FastAPI routes for running the RDTII extraction pipeline.

The HTTP adapter delegates to the same reviewer-contract functions used by ``run.py`` so
the CLI and API stay behaviorally aligned while the domain/orchestration code remains
framework-agnostic.
"""

from __future__ import annotations

from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from zetarix.domain.entities import Finding
from zetarix.orchestration.pipeline_service import (
    PipelineRequest,
    PipelineResult,
    run_pipeline,
)
from zetarix.orchestration.run_store import JsonRunRepository, RunRecord, utc_now

router = APIRouter(tags=["pipeline"])


SourceMode = Literal["gold", "live"]


class ExtractionRequest(BaseModel):
    country: str = Field(default="SG", description="Country code or name, e.g. SG/Singapore.")
    pillar: int = Field(default=6, ge=6, le=7, description="RDTII pillar: 6 or 7.")
    source: SourceMode = Field(default="gold", description="gold for offline DB, live for crawl.")
    limit: int | None = Field(default=None, ge=1)
    docs_dir: str | None = None


def _finding_id(finding: Finding, idx: int) -> str:
    parts = [
        finding.economy or "unknown",
        f"p{finding.pillar.value}",
        finding.indicator,
        finding.title,
        finding.article_section,
        str(idx),
    ]
    return "-".join(_slug(part) for part in parts if part)


def _slug(value: str) -> str:
    cleaned = []
    for ch in value.lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif cleaned and cleaned[-1] != "-":
            cleaned.append("-")
    return "".join(cleaned).strip("-")[:120] or "item"


def _frontend_finding(finding: Finding, idx: int) -> dict:
    return {
        "id": _finding_id(finding, idx),
        "title": finding.title,
        "lastUpdate": finding.last_update.isoformat() if finding.last_update else None,
        "url": finding.url,
        "scope": finding.scope,
        "provisions": finding.provisions or finding.verbatim_snippet,
        "impact": finding.impact,
        "pillar": finding.pillar.value,
        "indicator": finding.indicator,
        "indicatorLabel": finding.indicator,
        "confidence": finding.confidence,
        "reviewStatus": finding.review_status.value,
        "jurisdiction": finding.economy,
        "documentTitle": finding.title,
        "articleNumber": finding.article_section,
        "language": "en",
    }


def _api_response(result: PipelineResult) -> dict:
    return {
        "country": result.country,
        "pillar": result.pillar,
        "source": result.source,
        "processingTime": result.processing_time,
        "findings": [
            _frontend_finding(finding, idx)
            for idx, finding in enumerate(result.findings, start=1)
        ],
    }


def _run_summary(record: RunRecord) -> dict:
    return {
        "id": record.id,
        "status": record.status,
        "country": record.request.country,
        "pillar": record.request.pillar,
        "requestedSource": record.request.source,
        "source": record.source,
        "limit": record.request.limit,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
        "processingTime": record.processing_time,
        "findingCount": record.finding_count,
        "error": record.error,
    }


def _repository() -> JsonRunRepository:
    return JsonRunRepository()


def _run_pipeline(request: ExtractionRequest) -> PipelineResult:
    try:
        return run_pipeline(
            PipelineRequest(
                country=request.country,
                pillar=request.pillar,
                source=request.source,
                limit=request.limit,
                docs_dir=request.docs_dir,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/findings")
def list_findings(
    country: str = Query(default="SG"),
    pillar: int = Query(default=6, ge=6, le=7),
    source: SourceMode = Query(default="gold"),
    limit: int | None = Query(default=None, ge=1),
    docs_dir: str | None = Query(default=None),
) -> dict:
    """Return reviewer-ready findings from the CLI-equivalent extraction pipeline."""
    request = ExtractionRequest(
        country=country,
        pillar=pillar,
        source=source,
        limit=limit,
        docs_dir=docs_dir,
    )
    return _api_response(_run_pipeline(request))


@router.post("/pipeline/extract")
def extract_pipeline(request: ExtractionRequest) -> dict:
    """Run extraction from a structured request body."""
    return _api_response(_run_pipeline(request))


@router.post("/runs", status_code=201)
def create_run(request: ExtractionRequest) -> dict:
    """Run extraction and persist a durable run record.

    This is synchronous today. The route shape is intentionally compatible with a future
    Temporal-backed implementation where creation returns while workers continue.
    """
    run_id = uuid4().hex
    created_at = utc_now()
    repo = _repository()

    try:
        result = _run_pipeline(request)
        payload = _api_response(result)
        record = RunRecord(
            id=run_id,
            request=PipelineRequest(
                country=request.country,
                pillar=request.pillar,
                source=request.source,
                limit=request.limit,
                docs_dir=request.docs_dir,
            ),
            status="completed",
            created_at=created_at,
            updated_at=utc_now(),
            source=result.source,
            processing_time=result.processing_time,
            finding_count=len(result.findings),
            findings=payload["findings"],
        )
    except Exception as exc:
        record = RunRecord(
            id=run_id,
            request=PipelineRequest(
                country=request.country,
                pillar=request.pillar,
                source=request.source,
                limit=request.limit,
                docs_dir=request.docs_dir,
            ),
            status="failed",
            created_at=created_at,
            updated_at=utc_now(),
            error=str(exc),
        )

    repo.save(record)
    return {"run": _run_summary(record), "findings": record.findings}


@router.get("/runs")
def list_runs() -> dict:
    """List persisted extraction runs."""
    records = _repository().list()
    return {"runs": [_run_summary(record) for record in records]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    """Return one persisted extraction run."""
    record = _repository().get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": _run_summary(record)}


@router.get("/runs/{run_id}/findings")
def get_run_findings(run_id: str) -> dict:
    """Return reviewer-ready findings captured for one run."""
    record = _repository().get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": _run_summary(record), "findings": record.findings}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    """Cancel a non-terminal run.

    The current implementation executes synchronously, so completed/failed runs cannot be
    cancelled. Future Temporal-backed runs can map this route to workflow cancellation.
    """
    repo = _repository()
    record = repo.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    if record.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"run is already {record.status}")

    cancelled = RunRecord(
        id=record.id,
        request=record.request,
        status="cancelled",
        created_at=record.created_at,
        updated_at=utc_now(),
        source=record.source,
        processing_time=record.processing_time,
        finding_count=record.finding_count,
        findings=record.findings,
        error=record.error,
    )
    repo.save(cancelled)
    return {"run": _run_summary(cancelled)}

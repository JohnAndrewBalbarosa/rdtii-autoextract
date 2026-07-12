"""FastAPI routes for running the RDTII extraction pipeline.

The HTTP adapter delegates to the same reviewer-contract functions used by ``run.py`` so
the CLI and API stay behaviorally aligned while the domain/orchestration code remains
framework-agnostic.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from zetarix.domain.entities import Finding
from zetarix.orchestration.pipeline_service import (
    PipelineRequest,
    PipelineResult,
    run_pipeline,
)

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

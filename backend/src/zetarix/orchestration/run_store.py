"""Run persistence boundary for extraction workflows.

The production target is PostgreSQL, but this JSON repository gives the API a durable,
testable run contract today without coupling routes to a future database schema.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from zetarix.orchestration.pipeline_service import PipelineRequest

RunStatus = Literal["completed", "failed", "cancelled"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_run_store_path() -> Path:
    backend_root = Path(__file__).resolve().parents[3]
    return Path(os.environ.get("ZETARIX_RUN_STORE", backend_root / "data" / "runs" / "runs.json"))


@dataclass(frozen=True)
class RunRecord:
    id: str
    request: PipelineRequest
    status: RunStatus
    created_at: str
    updated_at: str
    source: str = ""
    processing_time: float | None = None
    finding_count: int = 0
    findings: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["request"] = asdict(self.request)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        request = PipelineRequest(**data["request"])
        return cls(
            id=data["id"],
            request=request,
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            source=data.get("source", ""),
            processing_time=data.get("processing_time"),
            finding_count=int(data.get("finding_count", 0)),
            findings=list(data.get("findings", [])),
            error=data.get("error"),
        )


class JsonRunRepository:
    """Small JSON-file repository for demo/local durable run state."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else default_run_store_path()

    def save(self, record: RunRecord) -> None:
        records = {item.id: item for item in self.list()}
        records[record.id] = record
        self._write(records.values())

    def get(self, run_id: str) -> RunRecord | None:
        for record in self.list():
            if record.id == run_id:
                return record
        return None

    def list(self) -> list[RunRecord]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return [RunRecord.from_dict(item) for item in payload.get("runs", [])]

    def _write(self, records) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(records, key=lambda item: item.created_at)
        temp_path = self._path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump({"runs": [record.to_dict() for record in ordered]}, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self._path)

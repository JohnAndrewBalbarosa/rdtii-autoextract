"""FastAPI pipeline endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from zetarix.app.pipeline_routes import list_findings
from zetarix.scoring import golden_dataset

_DOCS = golden_dataset._DEFAULT_DOCS_DIR
_HAS_DB = os.path.exists(os.path.join(_DOCS, "ESCAP-RDTII-2.1_ Round 1 Database.xlsx"))


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_findings_endpoint_returns_frontend_shape() -> None:
    payload = list_findings(
        country="SG",
        pillar=6,
        source="gold",
        limit=1,
        docs_dir=_DOCS,
    )

    assert payload["country"] == "Singapore"
    assert payload["pillar"] == 6
    assert payload["source"] == "gold"
    assert len(payload["findings"]) == 1

    finding = payload["findings"][0]
    assert finding["id"]
    assert finding["jurisdiction"] == "Singapore"
    assert finding["pillar"] == 6
    assert finding["indicator"].startswith("P6-")
    assert finding["reviewStatus"] == "pending"


def test_findings_endpoint_rejects_unknown_country() -> None:
    with pytest.raises(HTTPException) as exc:
        list_findings(country="Atlantis", pillar=6, source="gold", limit=None, docs_dir=None)
    assert exc.value.status_code == 400

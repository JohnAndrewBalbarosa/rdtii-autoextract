"""Offline, deterministic ``run.py --source live`` test using an injected fake fetcher.

No network, no LLM, no gold DB required: a fake fetcher returns a local fixture document
for the seed URL, and the real ``MockProvisionExtractor`` turns it into Findings. Asserts
the live path emits output.csv/json with NON-EMPTY ``Verbatim Snippet`` and
``Article / Section`` columns, exits 0, and is byte-for-byte deterministic.
"""

from __future__ import annotations

import csv
import os

import pytest

import run
from zetarix.transport.fetch_result import FetchResult
from zetarix.orchestration.output_emitter import CSV_COLUMNS

_FIXTURE_URL = "https://sso.agc.gov.sg/Act/PDPA2012"
_FIXTURE_HTML = (
    "<html><body>"
    "<h1>Personal Data Protection Act 2012</h1>"
    "<p>Section 26. An organisation shall not transfer any personal data to a country "
    "or territory outside Singapore except in accordance with this Act.</p>"
    "<p>Section 13. Consent of the individual is required before collecting personal "
    "data.</p>"
    "</body></html>"
)


class _FakeFetcher:
    """Returns a fixed in-memory HTML document for any URL (no network)."""

    def __init__(self, html: str) -> None:
        self._html = html

    def fetch_raw(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=self._html.encode("utf-8"),
        )


def _run_live(out_dir: str, monkeypatch) -> int:
    # Seed URLs come from the gold DB; pin them so the test needs no spreadsheets.
    monkeypatch.setattr(run, "_seed_urls", lambda *a, **k: [_FIXTURE_URL])
    # tag_discovery also reads the gold DB; stub it to a NEW pass-through (offline).
    monkeypatch.setattr(
        run,
        "tag_discovery",
        lambda findings, docs_dir=None: findings,
    )
    return run.main(
        ["--country", "SG", "--pillar", "6", "--source", "live", "--out-dir", out_dir],
        fetcher=_FakeFetcher(_FIXTURE_HTML),
        extractor=run._default_extractor(),
    )


def test_live_offline_emits_outputs_with_verbatim_and_section(tmp_path, monkeypatch):
    out_dir = str(tmp_path / "out")
    code = _run_live(out_dir, monkeypatch)
    assert code == 0

    csv_path = os.path.join(out_dir, "output.csv")
    json_path = os.path.join(out_dir, "output.json")
    assert os.path.exists(csv_path)
    assert os.path.exists(json_path)
    assert os.path.exists(os.path.join(out_dir, "logs", "run.log"))

    with open(csv_path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(CSV_COLUMNS)
    data_rows = rows[1:]
    assert data_rows, "live run with the mock must produce at least one finding"

    for row in data_rows:
        record = dict(zip(CSV_COLUMNS, row))
        assert record["Economy"] == "Singapore"
        assert record["Indicator ID"].startswith("P6-")
        # The keystone assertions: these columns are non-empty on the live path.
        assert record["Verbatim Snippet"].strip(), "Verbatim Snippet must be non-empty"
        assert record["Article / Section"].strip(), "Article / Section must be non-empty"
        assert record["Source URL"] == _FIXTURE_URL
        assert "[exact section text here]" not in record["Verbatim Snippet"]


def test_live_offline_is_deterministic(tmp_path, monkeypatch):
    out_a = str(tmp_path / "a")
    out_b = str(tmp_path / "b")
    assert _run_live(out_a, monkeypatch) == 0
    assert _run_live(out_b, monkeypatch) == 0

    with open(os.path.join(out_a, "output.csv"), encoding="utf-8") as handle:
        csv_a = handle.read()
    with open(os.path.join(out_b, "output.csv"), encoding="utf-8") as handle:
        csv_b = handle.read()
    assert csv_a == csv_b


def test_live_offline_skips_failed_fetch_without_crashing(tmp_path, monkeypatch):
    class _DeadFetcher:
        def fetch_raw(self, url: str) -> FetchResult:
            raise RuntimeError("network unreachable")

    out_dir = str(tmp_path / "out")
    monkeypatch.setattr(run, "_seed_urls", lambda *a, **k: [_FIXTURE_URL])
    monkeypatch.setattr(run, "tag_discovery", lambda findings, docs_dir=None: findings)
    monkeypatch.setattr(run, "build_gold_findings", lambda *a, **k: [])

    # All fetches fail -> live yields 0 findings -> gold fallback (stubbed empty).
    # Must still exit 0 and write a header-only CSV (no crash).
    code = run.main(
        ["--country", "SG", "--pillar", "6", "--source", "live", "--out-dir", out_dir],
        fetcher=_DeadFetcher(),
        extractor=run._default_extractor(),
    )
    assert code == 0
    assert os.path.exists(os.path.join(out_dir, "output.csv"))

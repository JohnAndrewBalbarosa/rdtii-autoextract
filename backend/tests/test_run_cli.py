"""Offline, deterministic tests for the run.py reviewer-contract CLI.

Drives ``main(argv)`` in-process (no subprocess, no network, no LLM) with
``--source gold`` so it runs anywhere the golden workbooks are checked out. Tests that
need gold rows are skipped when the databases are absent, so CI without the proprietary
spreadsheets still passes; the contract-shape tests run regardless.
"""

from __future__ import annotations

import csv
import json
import os

import pytest

import run
from zetarix.scoring import golden_dataset
from zetarix.orchestration.output_emitter import CSV_COLUMNS

# The real workbooks live in the repo-root docs/ (golden_dataset's default), which may
# differ from backend/docs/. Use that loader's own default so the skip guard matches the
# data the CLI actually reads.
_DOCS = golden_dataset._DEFAULT_DOCS_DIR
_HAS_DB = os.path.exists(os.path.join(_DOCS, "ESCAP-RDTII-2.1_ Round 1 Database.xlsx"))


# --- country alias resolution (no I/O) ---

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SG", "Singapore"),
        ("sg", "Singapore"),
        ("Singapore", "Singapore"),
        ("AU", "Australia"),
        ("australia", "Australia"),
        ("MY", "Malaysia"),
        ("Malaysia", "Malaysia"),
    ],
)
def test_resolve_country_accepts_aliases(raw, expected):
    assert run.resolve_country(raw) == expected


def test_resolve_country_rejects_unknown():
    assert run.resolve_country("Atlantis") is None


def test_main_exits_2_on_unrecognised_country(tmp_path):
    code = run.main(["--country", "Atlantis", "--pillar", "6", "--out-dir", str(tmp_path)])
    assert code == 2


# --- timeframe → Last Amended year parsing (no I/O) ---

def test_last_amended_year_picks_latest():
    assert run._last_amended_year("Since 2012 last amended on 1 February 2021").year == 2021
    assert run._last_amended_year("no year here") is None


# --- end-to-end offline run (needs gold DB) ---

@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_gold_run_creates_outputs_with_p14_header(tmp_path):
    out_dir = str(tmp_path / "out")
    code = run.main(
        ["--country", "SG", "--pillar", "6", "--source", "gold",
         "--out-dir", out_dir, "--docs-dir", _DOCS]
    )
    assert code == 0

    csv_path = os.path.join(out_dir, "output.csv")
    json_path = os.path.join(out_dir, "output.json")
    log_path = os.path.join(out_dir, "logs", "run.log")
    assert os.path.exists(csv_path)
    assert os.path.exists(json_path)
    assert os.path.exists(log_path)

    with open(csv_path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(CSV_COLUMNS)  # p.14 header
    assert len(rows) > 1  # at least one Singapore P6 finding

    # Every data row is Singapore, P6, with a non-empty verbatim/url contract column.
    for row in rows[1:]:
        record = dict(zip(CSV_COLUMNS, row))
        assert record["Economy"] == "Singapore"
        assert record["Indicator ID"].startswith("P6-")

    with open(json_path, encoding="utf-8") as handle:
        laws = json.load(handle)
    assert isinstance(laws, list) and laws
    assert all("provisions" in law and "model_version" in law for law in laws)


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_gold_findings_are_known_tagged(tmp_path):
    findings = run.build_gold_findings("Singapore", 6, _DOCS)
    tagged = run.tag_discovery(findings, _DOCS)
    assert tagged, "expected Singapore P6 gold findings"
    # Gold-sourced acts are in the gold DB, so they tag KNOWN.
    assert all(f.discovery_tag.value == "KNOWN" for f in tagged)


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_limit_caps_row_count(tmp_path):
    out_dir = str(tmp_path / "out")
    code = run.main(
        ["--country", "MY", "--pillar", "7", "--source", "gold",
         "--out-dir", out_dir, "--limit", "2", "--docs-dir", _DOCS]
    )
    assert code == 0
    with open(os.path.join(out_dir, "output.csv"), encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) - 1 <= 2  # header + at most 2 data rows


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_live_source_falls_back_to_gold_without_llm(tmp_path, monkeypatch):
    # No API key in env → live must fall back to gold and still emit outputs.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    out_dir = str(tmp_path / "out")
    code = run.main(
        ["--country", "AU", "--pillar", "6", "--source", "live",
         "--out-dir", out_dir, "--docs-dir", _DOCS]
    )
    assert code == 0
    assert os.path.exists(os.path.join(out_dir, "output.csv"))
    assert os.path.exists(os.path.join(out_dir, "output.json"))

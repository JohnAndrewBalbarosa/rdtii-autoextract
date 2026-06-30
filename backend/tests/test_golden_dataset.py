"""Integration tests for the golden dataset loader against the real RDTII workbooks.

Skipped automatically if the docs/ databases are not checked out, so CI without the
proprietary spreadsheets still passes.
"""

from __future__ import annotations

import os

import pytest

from zetarix.scoring.golden_dataset import (
    MANDATORY_PILLARS,
    load_gold_records,
    load_reference_items,
)

_DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
_HAS_DB = os.path.exists(os.path.join(_DOCS, "ESCAP-RDTII-2.1_ Round 1 Database.xlsx"))

pytestmark = pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")


@pytest.fixture(scope="module")
def gold():
    return load_gold_records(_DOCS)


def test_only_mandatory_pillars_loaded(gold):
    assert gold, "expected gold records to load"
    assert {r.pillar_id for r in gold} <= set(MANDATORY_PILLARS)


def test_section_header_rows_excluded(gold):
    # Every loaded record is a real indicator row (e.g. "6.1"), never a pillar name.
    assert all("." in r.indicator_id for r in gold)
    # Continuation rows may have a blank act, but every record stays matchable.
    assert all(r.act_name or r.urls for r in gold)


def test_multi_column_references_are_collected(gold):
    # At least some records carry more than one reference URL (the spilled columns).
    multi = [r for r in gold if len(r.urls) > 1]
    assert multi, "expected some records with multiple reference URLs"
    assert all(u.lower().startswith(("http", "www")) for r in gold for u in r.urls)


def test_round1_countries_present(gold):
    countries = {r.country for r in gold}
    assert {"Australia", "Singapore", "Malaysia"} <= countries


def test_reference_items_load(gold):
    refs = load_reference_items(_DOCS)
    assert refs
    assert all(item.act_name for item in refs)

"""Unit tests for the Round-1 output emitter (CSV p.14 + JSON p.15 contract)."""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from core.domain.entities import DiscoveryTag, Finding, Pillar
from core.pipeline.output_emitter import (
    CSV_COLUMNS,
    findings_to_csv_dicts,
    findings_to_json_objects,
    write_csv,
    write_json,
)


# The deck p.15 strong-row example: Thailand PDPA 2019, P6-I1, Section 26(2), NEW, 0.93.
def _thailand_pdpa() -> Finding:
    return Finding(
        title="Personal Data Protection Act 2019",
        last_update=date(2019, 5, 27),
        url="https://www.ratchakitcha.soc.go.th/pdpa-2019",
        scope="Cross-border transfer conditions",
        provisions="Conditions for sending personal data abroad.",
        impact="Restricts outbound personal-data transfers.",
        pillar=Pillar.CROSS_BORDER_DATA_FLOWS,
        indicator="P6-I1",
        confidence=0.93,
        economy="Thailand",
        law_number="B.E. 2562",
        article_section="Section 26(2)",
        discovery_tag=DiscoveryTag.NEW,
        verbatim_snippet="The data controller shall not send or transfer personal data to a foreign country...",
        mapping_rationale="Directly governs cross-border personal data transfer (Pillar 6).",
        location_ref="p.12",
        notes="Bilingual source (Thai/English).",
    )


# --- CSV header order/names ---

def test_csv_columns_match_p14_order_exactly():
    assert CSV_COLUMNS == (
        "Economy",
        "Law Name",
        "Law Number/Ref",
        "Last Amended",
        "Indicator ID",
        "Article / Section",
        "Discovery Tag",
        "Location Ref.",
        "Verbatim Snippet",
        "Mapping Rationale",
        "Source URL",
        "Confidence",
        "Notes",
    )


def test_csv_file_header_line_matches_contract(tmp_path):
    path = tmp_path / "output.csv"
    write_csv([_thailand_pdpa()], path)
    with open(path, encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == list(CSV_COLUMNS)


# --- CSV row mapping ---

def test_finding_maps_to_expected_csv_row_dict():
    row = findings_to_csv_dicts([_thailand_pdpa()])[0]
    assert row == {
        "Economy": "Thailand",
        "Law Name": "Personal Data Protection Act 2019",
        "Law Number/Ref": "B.E. 2562",
        "Last Amended": "2019",
        "Indicator ID": "P6-I1",
        "Article / Section": "Section 26(2)",
        "Discovery Tag": "NEW",
        "Location Ref.": "p.12",
        "Verbatim Snippet": "The data controller shall not send or transfer personal data to a foreign country...",
        "Mapping Rationale": "Directly governs cross-border personal data transfer (Pillar 6).",
        "Source URL": "https://www.ratchakitcha.soc.go.th/pdpa-2019",
        "Confidence": "0.93",
        "Notes": "Bilingual source (Thai/English).",
    }


def test_blank_optional_fields_render_empty_not_none():
    finding = Finding(
        title="Some Act",
        last_update=None,  # → blank Last Amended
        url="https://example.gov/act",
        scope="",
        provisions="",
        impact="",
        pillar=Pillar.DOMESTIC_DATA_PROTECTION,
        indicator="P7-I1",
        confidence=0.5,
        economy="Singapore",
    )
    row = findings_to_csv_dicts([finding])[0]
    assert row["Last Amended"] == ""
    assert row["Law Number/Ref"] == ""
    assert row["Location Ref."] == ""
    assert row["Discovery Tag"] == "KNOWN"  # default
    assert row["Confidence"] == "0.50"


# --- JSON grouping/envelope ---

def test_json_groups_by_law_with_provisions_and_metadata():
    laws = findings_to_json_objects([_thailand_pdpa()], model_version="m1", processing_time=1.5)
    assert len(laws) == 1
    law = laws[0]
    assert law["economy"] == "Thailand"
    assert law["law_name"] == "Personal Data Protection Act 2019"
    assert law["model_version"] == "m1"
    assert law["processing_time"] == 1.5
    assert "ocr_quality_cer" in law and "source_pdf_path" in law
    assert isinstance(law["provisions"], list) and len(law["provisions"]) == 1
    prov = law["provisions"][0]
    assert prov["indicator_id"] == "P6-I1"
    assert prov["article"] == "Section 26(2)"
    assert prov["discovery_tag"] == "NEW"
    assert prov["confidence"] == 0.93
    assert prov["source_url"] == "https://www.ratchakitcha.soc.go.th/pdpa-2019"
    assert "raw_context" in prov


def test_json_multiple_provisions_under_one_law():
    p6 = _thailand_pdpa()
    # Same economy+law_name, second indicator → one law, two provisions.
    from dataclasses import replace

    p6b = replace(p6, indicator="P6-I3", article_section="Section 27")
    laws = findings_to_json_objects([p6, p6b])
    assert len(laws) == 1
    assert [p["indicator_id"] for p in laws[0]["provisions"]] == ["P6-I1", "P6-I3"]


def test_json_source_pdf_path_lookup(tmp_path):
    laws = findings_to_json_objects(
        [_thailand_pdpa()],
        source_pdf_path_by_law={"Personal Data Protection Act 2019": "/pdfs/th_pdpa.pdf"},
    )
    assert laws[0]["source_pdf_path"] == "/pdfs/th_pdpa.pdf"


# --- empty inputs ---

def test_empty_findings_writes_header_only_csv(tmp_path):
    path = tmp_path / "empty.csv"
    write_csv([], path)
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows == [list(CSV_COLUMNS)]


def test_empty_findings_writes_empty_json_list(tmp_path):
    path = tmp_path / "empty.json"
    write_json([], path)
    with open(path, encoding="utf-8") as handle:
        assert json.load(handle) == []


def test_json_round_trips_non_ascii(tmp_path):
    from dataclasses import replace

    finding = replace(_thailand_pdpa(), title="พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล")
    path = tmp_path / "unicode.json"
    write_json([finding], path)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    assert data[0]["law_name"] == "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล"

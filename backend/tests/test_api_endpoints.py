from __future__ import annotations

from datetime import date

from zetarix.app import main
from zetarix.domain.entities import Finding, Pillar


def _reset_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("ZETARIX_FINDINGS_PATH", str(tmp_path / "findings.json"))
    main._repository.cache_clear()
    return main._repository()


def _finding() -> Finding:
    return Finding(
        title="Personal Data Protection Act 2012",
        last_update=date(2021, 1, 1),
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        scope="Applies to outbound transfers.",
        provisions="Section 26 prohibits transfer without safeguards.",
        impact="Conditional transfer regime.",
        pillar=Pillar.CROSS_BORDER_DATA_FLOWS,
        indicator="P6-I1",
        confidence=0.8,
        economy="Singapore",
        article_section="Section 26",
        verbatim_snippet="An organisation must not transfer personal data...",
        mapping_rationale="Direct transfer restriction.",
    )


def test_findings_review_statistics_and_export_round_trip(tmp_path, monkeypatch):
    repo = _reset_repo(tmp_path, monkeypatch)
    repo.replace_all([_finding()], metadata={"country": "Singapore", "source_used": "gold"})
    finding_id = repo.finding_id(_finding())

    findings = main.list_findings()
    assert findings[0].id == finding_id

    patch = main.patch_finding(
        finding_id,
        main.FindingPatchRequest(reviewStatus="verified", scope="Verified scope"),
    )
    assert patch.reviewStatus == "verified"
    assert patch.scope == "Verified scope"

    stats = main.statistics()
    assert stats["verified"] == 1

    exported_json = main.export_findings(format="json")
    assert b"Singapore" in exported_json.body

    exported_csv = main.export_findings(format="csv")
    assert exported_csv.media_type == "text/csv"
    assert "findings_export.csv" in exported_csv.headers["Content-Disposition"]


def test_pipeline_run_persists_results(tmp_path, monkeypatch):
    _reset_repo(tmp_path, monkeypatch)

    def fake_run_pipeline(_request):
        duplicate = Finding(
            title="Personal Data Protection Act 2012 ",
            last_update=_finding().last_update,
            url="https://sso.agc.gov.sg/Act/PDPA2012?utm_source=portal",
            scope=_finding().scope,
            provisions=_finding().provisions + " More detail.",
            impact=_finding().impact,
            pillar=_finding().pillar,
            indicator=_finding().indicator,
            confidence=0.9,
            economy=_finding().economy,
            article_section=_finding().article_section,
            verbatim_snippet=_finding().verbatim_snippet + " more",
            mapping_rationale=_finding().mapping_rationale,
        )
        return ([_finding(), duplicate], {"country": "Singapore", "pillar": 6, "source_used": "live"})

    monkeypatch.setattr(main, "_run_pipeline", fake_run_pipeline)
    body = main.run_pipeline(main.PipelineRunRequest(country="SG", pillar=6, source="live"))
    assert body["stored"] == 2
    assert body["statistics"]["total"] == 1

    findings = main.list_findings()
    assert findings[0].jurisdiction == "Singapore"
    assert findings[0].url == "https://sso.agc.gov.sg/Act/PDPA2012"
    assert findings[0].articleNumber == "Section 26"
    assert findings[0].verbatimSnippet
    assert findings[0].confidence == 0.9


def test_review_endpoint_persists_notes_and_live_metadata_survives_export(tmp_path, monkeypatch):
    repo = _reset_repo(tmp_path, monkeypatch)
    repo.replace_all([_finding()], metadata={"country": "Singapore", "pillar": 6, "source_used": "live"})
    finding_id = repo.finding_id(_finding())

    reviewed = main.review_finding(
        main.ReviewRequest(
            findingId=finding_id,
            status="rejected",
            notes="False positive during live review.",
        )
    )
    assert reviewed.reviewStatus == "rejected"
    assert reviewed.notes == "False positive during live review."

    fetched = main.get_finding(finding_id)
    assert fetched.notes == "False positive during live review."
    assert fetched.url == "https://sso.agc.gov.sg/Act/PDPA2012"
    assert fetched.articleNumber == "Section 26"
    assert fetched.verbatimSnippet
    assert fetched.mappingRationale

    stats = main.statistics()
    assert stats["metadata"]["source_used"] == "live"
    assert stats["reviewed"] == 1
    assert stats["rejected"] == 1

    exported = main.export_findings(format="json")
    assert b'"source_url":"https://sso.agc.gov.sg/Act/PDPA2012"' in exported.body
    assert b'"article":"Section 26"' in exported.body

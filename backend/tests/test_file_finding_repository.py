from __future__ import annotations

from datetime import date

from zetarix.domain.entities import Finding, Pillar, ReviewStatus
from zetarix.persistence.file_finding_repository import FileFindingRepository


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


def test_repository_persists_findings_and_review_updates(tmp_path):
    repo = FileFindingRepository(str(tmp_path / "findings.json"))
    repo.replace_all([_finding()], metadata={"source_used": "gold"})

    all_findings = repo.list_all()
    assert len(all_findings) == 1
    finding_id = repo.finding_id(all_findings[0])

    repo.update(
        finding_id,
        {
            "review_status": ReviewStatus.VERIFIED.value,
            "scope": "Updated scope",
            "article_number": "Section 26(1)",
        },
    )

    reloaded = FileFindingRepository(str(tmp_path / "findings.json"))
    updated = reloaded.get(finding_id)
    assert updated is not None
    assert updated.review_status is ReviewStatus.VERIFIED
    assert updated.scope == "Updated scope"
    assert updated.article_section == "Section 26(1)"
    assert reloaded.statistics()["verified"] == 1


def test_repository_collapses_duplicate_findings_for_same_legal_source(tmp_path):
    repo = FileFindingRepository(str(tmp_path / "findings.json"))
    base = _finding()
    duplicate = Finding(
        title="Personal Data Protection Act 2012 ",
        last_update=base.last_update,
        url="https://sso.agc.gov.sg/Act/PDPA2012?utm_source=portal",
        scope=base.scope,
        provisions=base.provisions + " Extra detail.",
        impact=base.impact,
        pillar=base.pillar,
        indicator=base.indicator,
        confidence=0.9,
        economy=base.economy,
        article_section=base.article_section,
        verbatim_snippet=base.verbatim_snippet + " With safeguards.",
        mapping_rationale=base.mapping_rationale,
    )

    repo.replace_all([base, duplicate], metadata={"source_used": "live"})

    all_findings = repo.list_all()
    assert len(all_findings) == 1
    assert all_findings[0].confidence == 0.9
    assert "Extra detail." in all_findings[0].provisions

"""Run live extraction on SG/AU/MY seed URLs and ingest real provision labels (Priority 1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

# run.py path bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import run as run_cli  # noqa: E402
from zetarix.domain.entities import Finding, Pillar  # noqa: E402
from zetarix.pretrain.dataset.build import build_datasets, count_examples, collect_examples, count_real_examples  # noqa: E402
from zetarix.pretrain.dataset.review_log import ReviewDecision, append_review_decision, load_review_decisions  # noqa: E402

_FOCUS = (
    ("SG", "Singapore", 6),
    ("SG", "Singapore", 7),
    ("AU", "Australia", 6),
    ("AU", "Australia", 7),
    ("MY", "Malaysia", 6),
    ("MY", "Malaysia", 7),
)
from zetarix.pretrain.paths import LIVE_FINDINGS_QUEUE_PATH

_MIN_PROVISION_CHARS = 20
_DEFAULT_OUT = LIVE_FINDINGS_QUEUE_PATH


def _finding_id_for(finding: Finding) -> str:
    key = f"{finding.economy}|{finding.pillar.value}|{finding.title}|{finding.provisions or finding.verbatim_snippet}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"live-{digest}"


def _finding_to_review(finding: Finding, *, status: str = "verified") -> ReviewDecision:
    from zetarix.domain.indicator_codes import to_db

    indicator = finding.indicator
    try:
        indicator = to_db(indicator)
    except ValueError:
        pass
    return ReviewDecision(
        finding_id=_finding_id_for(finding),
        review_status=status,  # type: ignore[arg-type]
        jurisdiction=finding.economy,
        pillar=finding.pillar.value,
        title=finding.title,
        scope=finding.scope,
        provisions=finding.provisions or finding.verbatim_snippet,
        impact=finding.impact,
        indicator=indicator,
        document_title=finding.title,
        article_number=finding.article_section,
        language="en",
    )


def extract_live_findings(
    *,
    docs_dir: str | None = None,
    fetcher=None,
    extractor=None,
    require_llm: bool = True,
) -> tuple[list[Finding], dict]:
    """Run ``run._build_live_findings`` for each focus country/pillar.

    Returns findings and provenance metadata proving which extractor ran.
    """
    os.environ.setdefault("ZETARIX_GROUNDING", "few_shot")
    os.environ.setdefault("ZETARIX_LLM_BACKEND", "local")
    os.environ.setdefault("OLLAMA_MODEL", "llama3.1:latest")

    import logging

    from zetarix.extraction.llm_provision_extractor import LLMProvisionExtractor
    from zetarix.extraction.mock_provision_extractor import MockProvisionExtractor
    from zetarix.inference.grounding import default_splits_dir, load_retriever

    logger = logging.getLogger("zetarix.ingest_live")
    logging.basicConfig(level=logging.INFO)
    all_findings: list[Finding] = []
    live_fetcher = fetcher or run_cli._default_fetcher()
    live_extractor = extractor or run_cli._default_extractor()

    extractor_name = type(live_extractor).__name__
    splits_dir = str(default_splits_dir())
    retriever_ok = load_retriever() is not None

    provenance = {
        "extractor_class": extractor_name,
        "extractor_module": type(live_extractor).__module__,
        "is_llm_provision_extractor": isinstance(live_extractor, LLMProvisionExtractor),
        "is_mock_provision_extractor": isinstance(live_extractor, MockProvisionExtractor),
        "splits_dir": splits_dir,
        "retriever_loaded": retriever_ok,
        "grounding": os.environ.get("ZETARIX_GROUNDING", "few_shot"),
        "llm_backend": os.environ.get("ZETARIX_LLM_BACKEND", "local"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.1:latest"),
        "findings_by_extractor_notes": {},
    }

    if require_llm and not isinstance(live_extractor, LLMProvisionExtractor):
        raise RuntimeError(
            f"Refusing to build queue with {extractor_name} — expected LLMProvisionExtractor. "
            f"splits_dir={splits_dir} retriever_loaded={retriever_ok}"
        )

    logger.info(
        "live extractor=%s splits=%s retriever=%s",
        extractor_name,
        splits_dir,
        retriever_ok,
    )

    for code, country, pillar in _FOCUS:
        findings = run_cli._build_live_findings(
            country, pillar, logger, docs_dir, live_fetcher, live_extractor
        )
        llm_count = sum(1 for f in findings if "LLM extraction" in (f.notes or ""))
        mock_count = sum(1 for f in findings if "mock keyword" in (f.mapping_rationale or ""))
        provenance["findings_by_extractor_notes"][f"{country}_P{pillar}"] = {
            "total": len(findings),
            "llm_notes": llm_count,
            "mock_rationale": mock_count,
        }
        print(f"{country} P{pillar}: {len(findings)} live finding(s) via {extractor_name}")
        all_findings.extend(findings)

    provenance["total_findings"] = len(all_findings)
    provenance["all_llm_notes"] = all(
        (provenance["findings_by_extractor_notes"][k]["mock_rationale"] == 0)
        for k in provenance["findings_by_extractor_notes"]
    ) if all_findings else True
    return all_findings, provenance


def ingest_findings_to_review(
    findings: list[Finding],
    *,
    min_provision_chars: int = _MIN_PROVISION_CHARS,
) -> int:
    """Append verified review decisions for findings with real provision text."""
    added = 0
    existing = {d.finding_id for d in load_review_decisions()}
    for finding in findings:
        text = (finding.provisions or finding.verbatim_snippet or "").strip()
        if len(text) < min_provision_chars:
            continue
        decision = _finding_to_review(finding)
        if decision.finding_id in existing:
            continue
        append_review_decision(decision)
        existing.add(decision.finding_id)
        added += 1
    return added


def _serialize_finding(f: Finding) -> dict:
    return {
        "title": f.title,
        "last_update": f.last_update.isoformat() if f.last_update else None,
        "url": f.url,
        "scope": f.scope,
        "provisions": f.provisions,
        "impact": f.impact,
        "pillar": f.pillar.value,
        "indicator": f.indicator,
        "confidence": f.confidence,
        "economy": f.economy,
        "article_section": f.article_section,
        "verbatim_snippet": f.verbatim_snippet,
        "mapping_rationale": f.mapping_rationale,
        "notes": f.notes,
    }


def report_real_label_counts() -> dict:
    law, tag = collect_examples()
    counts = count_examples(law, tag)
    real = count_real_examples(law, tag)
    return {
        "total_law": counts.law_interpreter_total,
        "total_tag": counts.tag_generator_total,
        "proxy_gold_law": sum(1 for ex in law if ex.source == "gold"),
        "real_provision_by_jurisdiction": real,
        "real_provision_total": {
            "law_interpreter": sum(v["law_interpreter"] for v in real.values()),
            "tag_generator": sum(v["tag_generator"] for v in real.values()),
        },
        "focus_jurisdictions_all": counts.focus_jurisdiction_totals,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live extraction + review log ingest for real labels.")
    parser.add_argument("--docs-dir", default=None)
    parser.add_argument("--out-queue", default=str(_DEFAULT_OUT))
    parser.add_argument("--rebuild", action="store_true", help="Rebuild datasets after ingest")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--queue-only", action="store_true", help="Only rebuild live_findings_queue.json (skip review ingest)")
    parser.add_argument("--allow-mock", action="store_true", help="Allow MockProvisionExtractor (default: require LLM)")
    args = parser.parse_args(argv)

    if args.report_only:
        print(json.dumps(report_real_label_counts(), indent=2))
        return 0

    findings, provenance = extract_live_findings(
        docs_dir=args.docs_dir,
        require_llm=not args.allow_mock,
    )
    queue_payload = {
        "provenance": provenance,
        "findings": [_serialize_finding(f) for f in findings],
    }
    Path(args.out_queue).write_text(
        json.dumps(queue_payload, indent=2),
        encoding="utf-8",
    )
    print("EXTRACTOR_PROVENANCE:", json.dumps(provenance, indent=2))

    if args.queue_only:
        return 0

    added = ingest_findings_to_review(findings)
    print(f"Ingested {added} review decisions with real provision text")

    if args.rebuild:
        build_datasets(docs_dir=args.docs_dir)

    print(json.dumps(report_real_label_counts(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

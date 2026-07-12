"""Eval harness for Law Interpreter and Tag Generator (Phase 4).

Runs zero-shot, few-shot/RAG, and fine-tuned conditions side by side on the held-out
test split. Writes JSON + Markdown reports with per-jurisdiction breakdowns.

Run full live eval (requires Ollama):
    cd backend
    export ZETARIX_LLM_BACKEND=local
    PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --live

Offline (oracle, CI):
    PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --offline
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, Sequence

from zetarix.domain.indicator_codes import to_db
from zetarix.llm.prompt_contracts import build_law_interpreter_prompt
from zetarix.scoring.scoring import _report
from zetarix.inference.few_shot import FewShotRetriever
from zetarix.inference.schemas import LAW_INTERPRETER_OUTPUT_SCHEMA
from zetarix.inference.set_trie import get_stats, reset_stats
from zetarix.pretrain.dataset.schemas import LawInterpreterExample, TagGeneratorExample
from zetarix.pretrain.paths import EVAL_REPORT_PATH, SPLITS_DIR
from zetarix.pretrain.train.export_ollama import resolve_stage_model

EvalMode = Literal["zero_shot", "few_shot", "system_prompt_baseline"]
StageName = Literal["law_interpreter", "tag_generator"]

_DEFAULT_SPLITS = SPLITS_DIR
_DEFAULT_REPORT = EVAL_REPORT_PATH
_DEFAULT_REPORT_MD = EVAL_REPORT_PATH.with_suffix(".md")
_F1_MARGIN = 0.05


class LLMCallable(Protocol):
    def __call__(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict: ...


@dataclass(frozen=True)
class LawInterpreterMetrics:
    obligation_type_accuracy: float
    scope_accuracy: float
    n: int
    obligation_type_correct: int
    scope_correct: int
    by_jurisdiction: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class TagGeneratorMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    n: int
    by_jurisdiction: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class StageEvalResult:
    mode: EvalMode
    law_interpreter: LawInterpreterMetrics | None
    tag_generator: TagGeneratorMetrics | None
    duration_sec: float = 0.0
    models_used: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalReport:
    results: tuple[StageEvalResult, ...]
    notes: str = ""
    test_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = ["=== Eval harness report ===", self.notes, ""]
        if self.test_counts:
            lines.append(
                f"Test split: law_interpreter={self.test_counts.get('law_interpreter', 0)} "
                f"tag_generator={self.test_counts.get('tag_generator', 0)}"
            )
            lines.append("")
        for result in self.results:
            lines.append(f"Mode: {result.mode} ({result.duration_sec:.1f}s)")
            if result.models_used:
                lines.append(f"  Models: {result.models_used}")
            if result.law_interpreter:
                li = result.law_interpreter
                lines.append(
                    f"  Law Interpreter: obligation_type_acc={li.obligation_type_accuracy:.3f} "
                    f"scope_acc={li.scope_accuracy:.3f} (n={li.n})"
                )
            if result.tag_generator:
                tg = result.tag_generator
                lines.append(
                    f"  Tag Generator: P={tg.precision:.3f} R={tg.recall:.3f} F1={tg.f1:.3f} "
                    f"(tp={tg.true_positives} fp={tg.false_positives} fn={tg.false_negatives}, n={tg.n})"
                )
            lines.append("")
        return "\n".join(lines)

    def to_markdown(self, verdict: str) -> str:
        lines = [
            "# Training eval report (Phase 4)",
            "",
            self.notes,
            "",
            "## Test split size",
            "",
            f"| Stage | Examples |",
            f"|-------|----------|",
            f"| Law Interpreter | {self.test_counts.get('law_interpreter', 0)} |",
            f"| Tag Generator | {self.test_counts.get('tag_generator', 0)} |",
            "",
            "## Results (all three conditions)",
            "",
            "| Mode | LI obligation acc | LI scope acc | TG precision | TG recall | TG F1 |",
            "|------|-------------------|--------------|--------------|-----------|-------|",
        ]
        for r in self.results:
            li_o = f"{r.law_interpreter.obligation_type_accuracy:.3f}" if r.law_interpreter else "—"
            li_s = f"{r.law_interpreter.scope_accuracy:.3f}" if r.law_interpreter else "—"
            tg_p = f"{r.tag_generator.precision:.3f}" if r.tag_generator else "—"
            tg_r = f"{r.tag_generator.recall:.3f}" if r.tag_generator else "—"
            tg_f = f"{r.tag_generator.f1:.3f}" if r.tag_generator else "—"
            lines.append(f"| {r.mode} | {li_o} | {li_s} | {tg_p} | {tg_r} | {tg_f} |")

        lines.extend(["", "## Verdict", "", verdict, ""])

        for r in self.results:
            if r.law_interpreter and r.law_interpreter.by_jurisdiction:
                lines.extend([f"### Law Interpreter by jurisdiction ({r.mode})", ""])
                for jurisdiction in sorted(r.law_interpreter.by_jurisdiction):
                    m = r.law_interpreter.by_jurisdiction[jurisdiction]
                    lines.append(
                        f"- **{jurisdiction}**: obligation={m.get('obligation_type_accuracy', 0):.3f} "
                        f"scope={m.get('scope_accuracy', 0):.3f}"
                    )
                lines.append("")
            if r.tag_generator and r.tag_generator.by_jurisdiction:
                lines.extend([f"### Tag Generator by jurisdiction ({r.mode})", ""])
                for jurisdiction in sorted(r.tag_generator.by_jurisdiction):
                    m = r.tag_generator.by_jurisdiction[jurisdiction]
                    lines.append(
                        f"- **{jurisdiction}**: P={m.get('precision', 0):.3f} "
                        f"R={m.get('recall', 0):.3f} F1={m.get('f1', 0):.3f}"
                    )
                lines.append("")

        return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _normalize_tags(tags: Sequence[str]) -> frozenset[str]:
    out: set[str] = set()
    for tag in tags:
        try:
            out.add(to_db(tag))
        except ValueError:
            cleaned = str(tag).strip()
            if cleaned:
                out.add(cleaned)
    return frozenset(out)


def _law_pair_correct(pred: dict[str, Any], ex: LawInterpreterExample) -> tuple[bool, bool]:
    obligation_ok = str(pred.get("obligation_type", "")).lower() == ex.obligation_type.lower()
    pred_scope = str(pred.get("scope", "")).strip().lower()
    gold_scope = ex.scope.strip().lower()
    scope_ok = pred_scope == gold_scope or bool(pred_scope and gold_scope and pred_scope in gold_scope)
    return obligation_ok, scope_ok


def score_law_interpreter(
    predictions: Sequence[dict[str, Any]],
    gold: Sequence[LawInterpreterExample],
) -> LawInterpreterMetrics:
    positives = [ex for ex in gold if ex.label == "positive"]
    n = min(len(predictions), len(positives))
    if n == 0:
        return LawInterpreterMetrics(0.0, 0.0, 0, 0, 0)

    obligation_correct = 0
    scope_correct = 0
    by_jurisdiction: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "obligation": 0, "scope": 0})

    for pred, ex in zip(predictions[:n], positives[:n], strict=False):
        ob_ok, sc_ok = _law_pair_correct(pred, ex)
        obligation_correct += int(ob_ok)
        scope_correct += int(sc_ok)
        bucket = by_jurisdiction[ex.jurisdiction]
        bucket["n"] += 1
        bucket["obligation"] += int(ob_ok)
        bucket["scope"] += int(sc_ok)

    juris_metrics = {
        j: {
            "obligation_type_accuracy": b["obligation"] / b["n"] if b["n"] else 0.0,
            "scope_accuracy": b["scope"] / b["n"] if b["n"] else 0.0,
            "n": b["n"],
        }
        for j, b in by_jurisdiction.items()
    }

    return LawInterpreterMetrics(
        obligation_type_accuracy=obligation_correct / n,
        scope_accuracy=scope_correct / n,
        n=n,
        obligation_type_correct=obligation_correct,
        scope_correct=scope_correct,
        by_jurisdiction=juris_metrics,
    )


def score_tag_generator(
    predictions: Sequence[dict[str, Any]],
    gold: Sequence[TagGeneratorExample],
) -> TagGeneratorMetrics:
    positives = [ex for ex in gold if ex.label == "positive"]
    n = min(len(predictions), len(positives))
    if n == 0:
        return TagGeneratorMetrics(0.0, 0.0, 0.0, 0, 0, 0, 0)

    tp = fp = fn = 0
    by_jurisdiction: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "n": 0})

    for pred, ex in zip(predictions[:n], positives[:n], strict=False):
        pred_tags = _normalize_tags(pred.get("indicator_tags") or [])
        gold_tags = _normalize_tags(ex.indicator_tags)
        tp += len(pred_tags & gold_tags)
        fp += len(pred_tags - gold_tags)
        fn += len(gold_tags - pred_tags)
        bucket = by_jurisdiction[ex.jurisdiction]
        bucket["tp"] += len(pred_tags & gold_tags)
        bucket["fp"] += len(pred_tags - gold_tags)
        bucket["fn"] += len(gold_tags - pred_tags)
        bucket["n"] += 1

    counts = _report(tp, fp, fn)
    juris_metrics = {}
    for j, b in by_jurisdiction.items():
        c = _report(b["tp"], b["fp"], b["fn"])
        juris_metrics[j] = {
            "precision": c.precision,
            "recall": c.recall,
            "f1": c.f1,
            "n": b["n"],
        }

    return TagGeneratorMetrics(
        precision=counts.precision,
        recall=counts.recall,
        f1=counts.f1,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        n=n,
        by_jurisdiction=juris_metrics,
    )


def _law_prompt(example: LawInterpreterExample, *, mode: EvalMode, retriever: FewShotRetriever | None) -> str:
    if mode == "few_shot" and retriever is not None:
        return retriever.build_law_interpreter_prompt(
            tagged_provision_input=example.tagged_provision_input,
            jurisdiction=example.jurisdiction,
            pillar=example.pillar,
        )
    return build_law_interpreter_prompt(
        tagged_provision_input=example.tagged_provision_input,
        jurisdiction=example.jurisdiction,
        pillar=example.pillar,
    )


def predict_law_batch(
    examples: Sequence[LawInterpreterExample],
    *,
    mode: EvalMode,
    llm: LLMCallable,
    retriever: FewShotRetriever | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    total = len(examples)
    for i, ex in enumerate(examples):
        prompt = _law_prompt(ex, mode=mode, retriever=retriever)
        try:
            outputs.append(llm(prompt, LAW_INTERPRETER_OUTPUT_SCHEMA, "law_interpreter"))
        except Exception as exc:
            outputs.append({"error": str(exc), "obligation_type": "other", "scope": "", "applicability_triggers": [], "plain_summary": ""})
        if on_progress:
            on_progress(i + 1, total)
    return outputs


def predict_tag_batch(
    examples: Sequence[TagGeneratorExample],
    *,
    mode: EvalMode,
    llm: LLMCallable,
    retriever: FewShotRetriever | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Route through production ``TagGenerator.generate()`` so SetTrie telemetry is real."""
    from zetarix.extraction.tag_generator import TagGenerator
    from zetarix.inference.set_trie import SetTrieTagger, reset_stats

    class _CallableLLMAdapter:
        """Bridge eval harness callables to the ``LLMProvider.complete`` interface."""

        def __init__(self, fn: LLMCallable) -> None:
            self.complete = fn

    reset_stats()
    grounding: Literal["none", "few_shot"] = "few_shot" if mode == "few_shot" else "none"
    trie = None
    if retriever is not None and retriever._tag_positives:
        trie = SetTrieTagger.from_examples(list(retriever._tag_positives))

    tagger = TagGenerator(
        _CallableLLMAdapter(llm),
        retriever=retriever if mode == "few_shot" else None,
        set_trie_tagger=trie,
        grounding=grounding,
    )

    outputs: list[dict[str, Any]] = []
    total = len(examples)
    for i, ex in enumerate(examples):
        try:
            mapping = tagger.generate(
                legal_interpretation=ex.legal_interpretation,
                jurisdiction=ex.jurisdiction,
                pillar=ex.pillar,
                precedent_tags=ex.precedent_tags,
            )
            outputs.append(
                {
                    "indicator_tags": list(mapping.indicator_tags),
                    "rationale": mapping.rationale,
                    "source": mapping.source,
                }
            )
        except Exception as exc:
            outputs.append({"error": str(exc), "indicator_tags": [], "rationale": ""})
        if on_progress:
            on_progress(i + 1, total)
    return outputs


def _models_for_mode(mode: EvalMode, base_model: str) -> dict[str, str]:
    if mode == "system_prompt_baseline":
        return {
            "law_interpreter": resolve_stage_model("law_interpreter", base_model),
            "tag_generator": resolve_stage_model("tag_generator", base_model),
        }
    return {"law_interpreter": base_model, "tag_generator": base_model}


def run_eval(
    *,
    splits_dir: Path | str = _DEFAULT_SPLITS,
    llm: LLMCallable,
    modes: Sequence[EvalMode] = ("zero_shot", "few_shot", "system_prompt_baseline"),
    max_examples: int | None = None,
    retriever: FewShotRetriever | None = None,
    base_model: str = "llama3.1:latest",
) -> EvalReport:
    root = Path(splits_dir)
    law_test = [LawInterpreterExample.from_dict(r) for r in _read_jsonl(root / "law_interpreter_test.jsonl")]
    tag_test = [TagGeneratorExample.from_dict(r) for r in _read_jsonl(root / "tag_generator_test.jsonl")]

    if max_examples is not None:
        law_test = law_test[:max_examples]
        tag_test = tag_test[:max_examples]

    if retriever is None:
        retriever = FewShotRetriever.from_splits_dir(root)

    results: list[StageEvalResult] = []
    notes_parts: list[str] = [
        "Metrics computed on held-out test split (stratified 80/10/10).",
        "Law Interpreter: obligation-type + scope classification accuracy.",
        "Tag Generator: micro-averaged precision/recall/F1 over indicator tags per finding.",
    ]

    system_prompt_tag = resolve_stage_model("law_interpreter", base_model)
    if system_prompt_tag.startswith("zetarix-") and "latest" in system_prompt_tag:
        notes_parts.append(
            "System-prompt baseline slot uses Ollama Modelfile-specialized adapters "
            f"({system_prompt_tag}) — NOT true QLoRA weights. "
            "Replace with QLoRA GGUF when adapters are trained."
        )

    reset_stats()
    for mode in modes:
        started = time.perf_counter()
        models = _models_for_mode(mode, base_model)

        def _progress(done: int, total: int) -> None:
            print(f"  [{mode}] {done}/{total}", file=sys.stderr, end="\r", flush=True)

        law_preds = predict_law_batch(
            law_test,
            mode=mode,
            llm=llm,
            retriever=retriever if mode == "few_shot" else None,
            on_progress=_progress,
        )
        tag_preds = predict_tag_batch(
            tag_test,
            mode=mode,
            llm=llm,
            retriever=retriever if mode == "few_shot" else None,
            on_progress=_progress,
        )
        print(file=sys.stderr)

        trie_stats = get_stats().to_dict()
        models_used = dict(models)
        models_used["set_trie"] = json.dumps(trie_stats)
        results.append(
            StageEvalResult(
                mode=mode,
                law_interpreter=score_law_interpreter(law_preds, law_test),
                tag_generator=score_tag_generator(tag_preds, tag_test),
                duration_sec=time.perf_counter() - started,
                models_used=models_used,
            )
        )

    return EvalReport(
        results=tuple(results),
        notes="\n".join(notes_parts),
        test_counts={"law_interpreter": len(law_test), "tag_generator": len(tag_test)},
    )


def _oracle_llm_factory(
    law_gold: Sequence[LawInterpreterExample],
    tag_gold: Sequence[TagGeneratorExample],
) -> LLMCallable:
    def _complete(prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "law_interpreter":
            for ex in law_gold:
                if ex.tagged_provision_input in prompt or ex.jurisdiction in prompt:
                    return {
                        "obligation_type": ex.obligation_type,
                        "scope": ex.scope,
                        "applicability_triggers": list(ex.applicability_triggers),
                        "plain_summary": ex.plain_summary,
                    }
        if agent_profile == "tag_generator":
            for ex in tag_gold:
                if ex.legal_interpretation in prompt or ex.jurisdiction in prompt:
                    return {
                        "indicator_tags": list(ex.indicator_tags),
                        "rationale": ex.rationale,
                    }
        return {}

    return _complete


def run_offline_eval(splits_dir: Path | str = _DEFAULT_SPLITS, max_examples: int = 5) -> EvalReport:
    root = Path(splits_dir)
    law_test = [LawInterpreterExample.from_dict(r) for r in _read_jsonl(root / "law_interpreter_test.jsonl")][:max_examples]
    tag_test = [TagGeneratorExample.from_dict(r) for r in _read_jsonl(root / "tag_generator_test.jsonl")][:max_examples]
    llm = _oracle_llm_factory(law_test, tag_test)
    retriever = FewShotRetriever.from_splits_dir(root)
    return run_eval(
        splits_dir=root,
        llm=llm,
        modes=("zero_shot", "few_shot", "system_prompt_baseline"),
        max_examples=max_examples,
        retriever=retriever,
    )


def compare_baselines(report: EvalReport) -> str:
    by_mode = {r.mode: r for r in report.results}
    zero = by_mode.get("zero_shot")
    few = by_mode.get("few_shot")
    sp = by_mode.get("system_prompt_baseline")

    parts: list[str] = []

    if zero and few and zero.tag_generator and few.tag_generator:
        rag_gain = few.tag_generator.f1 - zero.tag_generator.f1
        parts.append(
            f"Few-shot/RAG vs zero-shot: Tag Generator F1 delta = {rag_gain:+.3f} "
            f"({few.tag_generator.f1:.3f} vs {zero.tag_generator.f1:.3f})."
        )

    if few and sp and few.tag_generator and sp.tag_generator:
        margin = sp.tag_generator.f1 - few.tag_generator.f1
        if margin >= _F1_MARGIN:
            parts.append(
                f"System-prompt baseline beats few-shot/RAG by {margin:.3f} F1 — worth deploying."
            )
        else:
            parts.append(
                f"System-prompt baseline does NOT beat few-shot/RAG by a meaningful margin "
                f"(delta F1={margin:+.3f}). Prefer the RAG-grounded baseline."
            )
    elif sp is None or few is None:
        parts.append(
            "Could not compare all three modes — missing few_shot or system_prompt_baseline results."
        )

    if zero and few and zero.law_interpreter and few.law_interpreter:
        li_gain = few.law_interpreter.obligation_type_accuracy - zero.law_interpreter.obligation_type_accuracy
        parts.append(
            f"Law Interpreter obligation accuracy: few-shot {few.law_interpreter.obligation_type_accuracy:.3f} "
            f"vs zero-shot {zero.law_interpreter.obligation_type_accuracy:.3f} (delta {li_gain:+.3f})."
        )

    return " ".join(parts) if parts else "Insufficient data for comparison."


def write_reports(report: EvalReport, verdict: str, *, out_json: Path, out_md: Path) -> None:
    payload = report.to_dict()
    payload["verdict"] = verdict
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(report.to_markdown(verdict), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Law Interpreter / Tag Generator eval harness.")
    parser.add_argument("--splits-dir", default=str(_DEFAULT_SPLITS))
    parser.add_argument("--out", default=str(_DEFAULT_REPORT))
    parser.add_argument("--out-md", default=str(_DEFAULT_REPORT_MD))
    parser.add_argument("--offline", action="store_true", help="Oracle LLM for CI (no API keys)")
    parser.add_argument("--live", action="store_true", help="Run live eval via LLMRouter + Ollama")
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--base-model", default=os.environ.get("OLLAMA_MODEL", "llama3.1:latest"))
    args = parser.parse_args(argv)

    if args.offline:
        report = run_offline_eval(args.splits_dir, max_examples=args.max_examples or 5)
    else:
        os.environ.setdefault("ZETARIX_GROUNDING", "few_shot")
        os.environ.setdefault("ZETARIX_LLM_BACKEND", "local")
        if args.live:
            os.environ.setdefault("OLLAMA_MODEL", args.base_model)
            os.environ.setdefault("OLLAMA_MODEL_LAW_INTERPRETER", "zetarix-law-interpreter:latest")
            os.environ.setdefault("OLLAMA_MODEL_TAG_GENERATOR", "zetarix-tag-generator:latest")

        from zetarix.llm.router import LLMRouter

        router = LLMRouter.from_env()
        report = run_eval(
            splits_dir=args.splits_dir,
            llm=router.complete,
            max_examples=args.max_examples,
            base_model=args.base_model,
        )

    verdict = compare_baselines(report)
    write_reports(report, verdict, out_json=Path(args.out), out_md=Path(args.out_md))
    print(report.summary())
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

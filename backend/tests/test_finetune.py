"""Tests for Phase 3 LoRA fine-tune formatting and Ollama export."""

from __future__ import annotations

import json
import os
from pathlib import Path

from zetarix.llm.local_provider import LocalLLMProvider
from zetarix.training.export_ollama import OllamaExportConfig, resolve_stage_model, write_modelfile
from zetarix.training.finetune import (
    FinetuneConfig,
    format_law_interpreter_row,
    format_splits,
    format_tag_generator_row,
)


def test_format_law_interpreter_row_negative_label():
    row = format_law_interpreter_row(
        {
            "jurisdiction": "Malaysia",
            "pillar": 6,
            "tagged_provision_input": "test",
            "obligation_type": "prohibition",
            "scope": "scope",
            "applicability_triggers": [],
            "plain_summary": "summary",
            "label": "negative",
        }
    )
    assert '"reject": true' in row["text"] or '"reject": true' in row["text"].lower()


def test_format_splits_writes_chat_jsonl(tmp_path):
    splits = tmp_path / "splits"
    splits.mkdir()
    sample = {
        "tagged_provision_input": "Act: PDPA",
        "jurisdiction": "Singapore",
        "pillar": 6,
        "obligation_type": "requirement",
        "scope": "orgs",
        "applicability_triggers": [],
        "plain_summary": "summary",
        "label": "positive",
    }
    (splits / "law_interpreter_train.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    out = tmp_path / "formatted"
    written = format_splits(splits, out)
    assert "law_interpreter_train" in written
    line = (out / "law_interpreter_train_chat.jsonl").read_text(encoding="utf-8").strip()
    assert "text" in json.loads(line)


def test_write_modelfile_for_stage(tmp_path):
    cfg = OllamaExportConfig(stage="law_interpreter", export_dir=tmp_path)
    path = write_modelfile(cfg)
    content = path.read_text(encoding="utf-8")
    assert "FROM llama3.1:latest" in content
    assert "Law Interpreter" in content


def test_resolve_stage_model_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_LAW_INTERPRETER", "zetarix-law-interpreter:latest")
    assert resolve_stage_model("law_interpreter", "llama3.1:latest") == "zetarix-law-interpreter:latest"


def test_local_provider_picks_stage_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_TAG_GENERATOR", "zetarix-tag-generator:latest")
    provider = LocalLLMProvider(model="llama3.1:latest")
    assert provider._model_for("tag_generator") == "zetarix-tag-generator:latest"
    assert provider._model_for("main_controller") == "llama3.1:latest"

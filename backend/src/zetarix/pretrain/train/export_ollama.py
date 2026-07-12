"""Export fine-tuned LoRA adapters for Ollama deployment (Phase 3)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from zetarix.pretrain.paths import TRAINING_DATA_DIR

StageName = Literal["law_interpreter", "tag_generator"]

_DEFAULT_ADAPTERS = TRAINING_DATA_DIR / "adapters"
_DEFAULT_EXPORT = TRAINING_DATA_DIR / "ollama"

_STAGE_SYSTEM: dict[str, str] = {
    "law_interpreter": (
        "You are the RDTII Law Interpreter. Given a tagged legal provision, return JSON only "
        "with obligation_type, scope, applicability_triggers, and plain_summary."
    ),
    "tag_generator": (
        "You are the RDTII Law-Aware Tag Generator. Given a legal interpretation, return JSON only "
        "with indicator_tags and rationale."
    ),
}


@dataclass(frozen=True)
class OllamaExportConfig:
    stage: StageName
    base_ollama_model: str = "llama3.1:latest"
    adapter_dir: Path = _DEFAULT_ADAPTERS
    export_dir: Path = _DEFAULT_EXPORT
    temperature: float = 0.1

    @property
    def tag(self) -> str:
        return f"zetarix-{self.stage}:latest"

    @property
    def adapter_path(self) -> Path:
        return self.adapter_dir / self.stage

    @property
    def modelfile_path(self) -> Path:
        return self.export_dir / f"Modelfile.{self.stage}"


def write_modelfile(config: OllamaExportConfig, *, gguf_path: Path | None = None) -> Path:
    """Write an Ollama Modelfile for the fine-tuned stage.

    If ``gguf_path`` is set, the Modelfile points at the merged GGUF. Otherwise it
    documents the base model + system prompt (use after ``ollama create`` with merged weights).
    """
    config.export_dir.mkdir(parents=True, exist_ok=True)
    from_line = f"FROM {gguf_path}" if gguf_path else f"FROM {config.base_ollama_model}"
    system = _STAGE_SYSTEM[config.stage]
    content = (
        f"{from_line}\n"
        f"PARAMETER temperature {config.temperature}\n"
        f'SYSTEM """{system}"""\n'
    )
    config.modelfile_path.write_text(content, encoding="utf-8")
    return config.modelfile_path


def write_export_manifest(config: OllamaExportConfig) -> Path:
    """Write merge/convert instructions when GGUF is not yet produced."""
    manifest = config.export_dir / f"export_{config.stage}.md"
    manifest.write_text(
        f"""# Export {config.stage} adapter to Ollama

## Prerequisites
- LoRA adapter at `{config.adapter_path}/`
- Base weights: `{config.base_ollama_model}` (Ollama) or HuggingFace `meta-llama/Meta-Llama-3-8B-Instruct`

## Option A — Unsloth (recommended)
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="{config.adapter_path}",
    max_seq_length=2048,
    load_in_4bit=True,
)
model.save_pretrained_gguf("{config.export_dir}/{config.stage}", tokenizer, quantization_method="q4_k_m")
```

## Option B — llama.cpp
```bash
# 1. Merge LoRA into base (Python peft merge_and_unload or unsloth)
# 2. Convert to GGUF:
python -m llama_cpp.convert_hf_to_gguf merged-{config.stage}/ --outfile {config.export_dir}/{config.stage}.gguf
```

## Create Ollama model
```bash
ollama create {config.tag} -f {config.modelfile_path}
```

## Point Zetarix at the adapter
```bash
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL_{config.stage.upper()}={config.tag}
# or single model fallback:
export OLLAMA_MODEL={config.tag}
```
""",
        encoding="utf-8",
    )
    return manifest


def ollama_create(config: OllamaExportConfig, *, gguf_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``ollama create`` using the generated Modelfile."""
    modelfile = write_modelfile(config, gguf_path=gguf_path)
    return subprocess.run(
        ["ollama", "create", config.tag, "-f", str(modelfile)],
        check=True,
        capture_output=True,
        text=True,
    )


def model_env_var(stage: StageName) -> str:
    return f"OLLAMA_MODEL_{stage.upper()}"


def resolve_stage_model(stage: StageName, default: str) -> str:
    """Resolve Ollama model tag for a pipeline stage from env."""
    specific = os.environ.get(model_env_var(stage), "").strip()
    if specific:
        return specific
    fallback = os.environ.get(f"OLLAMA_MODEL_{stage.replace('_', '').upper()}", "").strip()
    if fallback:
        return fallback
    # law_interpreter -> OLLAMA_MODEL_LAW_INTERPRETER handled above; also check JSON map
    raw_map = os.environ.get("OLLAMA_MODEL_MAP", "").strip()
    if raw_map:
        try:
            mapping = json.loads(raw_map)
            if stage in mapping:
                return str(mapping[stage])
        except json.JSONDecodeError:
            pass
    return default

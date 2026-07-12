"""LoRA fine-tune helpers for Law Interpreter and Tag Generator (Phase 3).

Uses QLoRA via Unsloth when available, otherwise transformers+peft+bitsandbytes.
4-bit only — no full fine-tuning.

Regenerate chat-formatted datasets:
    cd backend && PYTHONPATH=src python -m zetarix.pretrain.train.finetune --format-only

Train locally (GPU + requirements-train.txt):
    cd backend && PYTHONPATH=src python -m zetarix.pretrain.train.finetune --stage law_interpreter --train

Export for Ollama:
    cd backend && PYTHONPATH=src python -m zetarix.pretrain.train.finetune --stage law_interpreter --export-ollama

Colab fallback:
    cd backend && PYTHONPATH=src python -m zetarix.pretrain.train.finetune --print-colab --stage law_interpreter
    # or open notebooks/finetune_colab.ipynb
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from zetarix.inference.schemas import LAW_INTERPRETER_OUTPUT_SCHEMA, TAG_GENERATOR_OUTPUT_SCHEMA
from zetarix.pretrain.paths import TRAINING_DATA_DIR
from zetarix.pretrain.train.export_ollama import OllamaExportConfig, write_export_manifest, write_modelfile

StageName = Literal["law_interpreter", "tag_generator"]

_DEFAULT_DATA = TRAINING_DATA_DIR / "splits"
_DEFAULT_FORMATTED = TRAINING_DATA_DIR / "formatted"
_DEFAULT_ADAPTERS = TRAINING_DATA_DIR / "adapters"

# Starting hyperparameters — tune against val loss, not fixed.
DEFAULT_LORA_RANK = 16
DEFAULT_LORA_ALPHA = 32
DEFAULT_LEARNING_RATE = 2e-4
DEFAULT_EPOCHS = 3
DEFAULT_BASE_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"
# Open alternative if HF gated model is unavailable:
_FALLBACK_BASE_MODEL = "NousResearch/Meta-Llama-3-8B-Instruct"

_LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


@dataclass(frozen=True)
class FinetuneConfig:
    stage: StageName
    base_model: str = DEFAULT_BASE_MODEL
    lora_rank: int = DEFAULT_LORA_RANK
    lora_alpha: int = DEFAULT_LORA_ALPHA
    learning_rate: float = DEFAULT_LEARNING_RATE
    epochs: int = DEFAULT_EPOCHS
    max_seq_length: int = 1024  # 8 GB VRAM safe default
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    formatted_dir: Path = _DEFAULT_FORMATTED
    adapter_dir: Path = _DEFAULT_ADAPTERS

    @property
    def ollama_tag(self) -> str:
        return f"zetarix-{self.stage}:latest"

    @property
    def train_file(self) -> Path:
        return self.formatted_dir / f"{self.stage}_train_chat.jsonl"

    @property
    def val_file(self) -> Path:
        return self.formatted_dir / f"{self.stage}_val_chat.jsonl"

    @property
    def output_adapter_dir(self) -> Path:
        return self.adapter_dir / self.stage


def _llama3_chat(system: str, user: str, assistant: str) -> str:
    return (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{assistant}<|eot_id|>"
    )


def format_law_interpreter_row(row: dict[str, Any]) -> dict[str, str]:
    system = (
        "You are the RDTII Law Interpreter. Given a tagged legal provision, return JSON with "
        "obligation_type, scope, applicability_triggers, and plain_summary."
    )
    user = (
        f"Jurisdiction: {row['jurisdiction']}\n"
        f"Pillar: {row['pillar']}\n\n"
        f"{row['tagged_provision_input']}"
    )
    if row.get("label") == "negative":
        assistant_obj: dict[str, Any] = {"reject": True, "reason": "Reviewer rejected this interpretation."}
    else:
        assistant_obj = {
            "obligation_type": row["obligation_type"],
            "scope": row["scope"],
            "applicability_triggers": list(row.get("applicability_triggers") or []),
            "plain_summary": row["plain_summary"],
        }
    return {"text": _llama3_chat(system, user, json.dumps(assistant_obj, ensure_ascii=False))}


def format_tag_generator_row(row: dict[str, Any]) -> dict[str, str]:
    system = (
        "You are the RDTII Law-Aware Tag Generator. Given a legal interpretation, return JSON "
        "with indicator_tags and rationale."
    )
    precedent = ", ".join(row.get("precedent_tags") or []) or "(none)"
    user = (
        f"Jurisdiction: {row['jurisdiction']}\n"
        f"Pillar: {row['pillar']}\n"
        f"Precedent tags: {precedent}\n\n"
        f"{row['legal_interpretation']}"
    )
    if row.get("label") == "negative":
        assistant = json.dumps({"indicator_tags": [], "rationale": "Reviewer rejected this mapping."})
    else:
        assistant = json.dumps(
            {
                "indicator_tags": list(row.get("indicator_tags") or []),
                "rationale": row.get("rationale", ""),
            },
            ensure_ascii=False,
        )
    return {"text": _llama3_chat(system, user, assistant)}


def format_splits(
    splits_dir: Path | str = _DEFAULT_DATA,
    out_dir: Path | str = _DEFAULT_FORMATTED,
) -> dict[str, Path]:
    """Write Llama-3 chat-formatted JSONL for each stage and split."""
    root = Path(splits_dir)
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    formatters = {
        "law_interpreter": format_law_interpreter_row,
        "tag_generator": format_tag_generator_row,
    }
    written: dict[str, Path] = {}
    for stage, formatter in formatters.items():
        for split in ("train", "val", "test"):
            src = root / f"{stage}_{split}.jsonl"
            if not src.exists():
                continue
            dst = output / f"{stage}_{split}_chat.jsonl"
            with src.open(encoding="utf-8") as handle, dst.open("w", encoding="utf-8") as out:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    out.write(json.dumps(formatter(json.loads(line)), ensure_ascii=False) + "\n")
            written[f"{stage}_{split}"] = dst
    return written


def _require_train_files(config: FinetuneConfig) -> None:
    if not config.train_file.exists():
        raise FileNotFoundError(
            f"Missing {config.train_file}. Run: python -m zetarix.pretrain.train.finetune --format-only"
        )


@dataclass
class TrainResult:
    adapter_dir: Path
    train_loss: float | None = None
    eval_loss: float | None = None
    backend: str = "peft"


def train_unsloth(config: FinetuneConfig) -> TrainResult:
    """Train with Unsloth 4-bit QLoRA (fastest path)."""
    from unsloth import FastLanguageModel  # type: ignore
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from datasets import load_dataset

    _require_train_files(config)
    config.output_adapter_dir.mkdir(parents=True, exist_ok=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.base_model,
        max_seq_length=config.max_seq_length,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        target_modules=_LORA_TARGETS,
    )

    data_files: dict[str, str] = {"train": str(config.train_file)}
    if config.val_file.exists():
        data_files["validation"] = str(config.val_file)
    ds = load_dataset("json", data_files=data_files)

    args = TrainingArguments(
        output_dir=str(config.output_adapter_dir / "checkpoints"),
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        warmup_steps=10,
        num_train_epochs=config.epochs,
        learning_rate=config.learning_rate,
        logging_steps=5,
        eval_strategy="epoch" if "validation" in ds else "no",
        save_strategy="epoch",
        fp16=False,
        bf16=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds["train"],
        eval_dataset=ds.get("validation"),
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
        args=args,
    )
    train_output = trainer.train()
    model.save_pretrained(str(config.output_adapter_dir))
    tokenizer.save_pretrained(str(config.output_adapter_dir))

    eval_loss = None
    if "validation" in ds:
        metrics = trainer.evaluate()
        eval_loss = metrics.get("eval_loss")

    return TrainResult(
        adapter_dir=config.output_adapter_dir,
        train_loss=train_output.training_loss,
        eval_loss=eval_loss,
        backend="unsloth",
    )


def train_peft(config: FinetuneConfig) -> TrainResult:
    """Train with transformers+peft+bitsandbytes QLoRA (portable fallback)."""
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
    from trl import SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU required for QLoRA training. Use --print-colab or notebooks/finetune_colab.ipynb."
        )

    _require_train_files(config)
    config.output_adapter_dir.mkdir(parents=True, exist_ok=True)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    base_model = config.base_model
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    try:
        tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb,
            device_map="auto",
            token=token,
        )
    except OSError:
        base_model = _FALLBACK_BASE_MODEL
        tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb,
            device_map="auto",
            token=token,
        )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = prepare_model_for_kbit_training(model)
    lora = LoraConfig(
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        target_modules=_LORA_TARGETS,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)

    data_files: dict[str, str] = {"train": str(config.train_file)}
    if config.val_file.exists():
        data_files["validation"] = str(config.val_file)
    ds = load_dataset("json", data_files=data_files)

    args = TrainingArguments(
        output_dir=str(config.output_adapter_dir / "checkpoints"),
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        warmup_steps=10,
        num_train_epochs=config.epochs,
        learning_rate=config.learning_rate,
        logging_steps=5,
        eval_strategy="epoch" if "validation" in ds else "no",
        save_strategy="epoch",
        fp16=False,
        bf16=True,
        report_to="none",
        optim="paged_adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=ds["train"],
        eval_dataset=ds.get("validation"),
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
        args=args,
    )
    train_output = trainer.train()
    model.save_pretrained(str(config.output_adapter_dir))
    tokenizer.save_pretrained(str(config.output_adapter_dir))

    eval_loss = None
    if "validation" in ds:
        metrics = trainer.evaluate()
        eval_loss = metrics.get("eval_loss")

    return TrainResult(
        adapter_dir=config.output_adapter_dir,
        train_loss=train_output.training_loss,
        eval_loss=eval_loss,
        backend="peft",
    )


def run_local_finetune(config: FinetuneConfig) -> TrainResult:
    """Train with Unsloth if installed, else peft+bitsandbytes."""
    try:
        import unsloth  # noqa: F401

        return train_unsloth(config)
    except ImportError:
        return train_peft(config)


def export_ollama_artifacts(config: FinetuneConfig) -> dict[str, Path]:
    """Write Modelfile + export instructions for Ollama deployment."""
    export_cfg = OllamaExportConfig(stage=config.stage, adapter_dir=config.adapter_dir)
    paths = {
        "modelfile": write_modelfile(export_cfg),
        "manifest": write_export_manifest(export_cfg),
    }
    if config.output_adapter_dir.exists():
        meta = config.output_adapter_dir / "training_meta.json"
        meta.write_text(
            json.dumps(
                {
                    "stage": config.stage,
                    "base_model": config.base_model,
                    "lora_rank": config.lora_rank,
                    "lora_alpha": config.lora_alpha,
                    "learning_rate": config.learning_rate,
                    "epochs": config.epochs,
                    "ollama_tag": config.ollama_tag,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        paths["meta"] = meta
    return paths


def colab_instructions(config: FinetuneConfig) -> str:
    """Exact remote-training steps when local GPU compute is unavailable."""
    return f"""
# Colab / Kaggle QLoRA fine-tune — {config.stage}

Open `backend/notebooks/finetune_colab.ipynb` in Colab (GPU runtime T4/L4/A100).

Or run manually:

## 1. Upload formatted datasets
After `python -m zetarix.pretrain.train.finetune --format-only`, upload:
- `{config.train_file}`
- `{config.val_file}`

## 2. Install Unsloth
```bash
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps trl peft accelerate bitsandbytes datasets transformers
```

## 3. Train (4-bit QLoRA — starting hyperparameters, tune on val loss)
```python
from zetarix.pretrain.train.finetune import FinetuneConfig, train_unsloth
config = FinetuneConfig(stage="{config.stage}", epochs={config.epochs})
result = train_unsloth(config)
print(result)
```

## 4. Export GGUF + create Ollama model
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained("{config.output_adapter_dir}")
model.save_pretrained_gguf("zetarix-{config.stage}", tokenizer, quantization_method="q4_k_m")
```
```bash
ollama create {config.ollama_tag} -f Modelfile.{config.stage}
```

## 5. Point Zetarix at the adapter
```bash
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL_LAW_INTERPRETER=zetarix-law-interpreter:latest
export OLLAMA_MODEL_TAG_GENERATOR=zetarix-tag-generator:latest
```

Hyperparameters are a **starting point** (rank={config.lora_rank}, alpha={config.lora_alpha},
lr={config.learning_rate}, epochs={config.epochs}). Tune against validation loss before deploying.
""".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Format, train, and export LoRA adapters.")
    parser.add_argument("--format-only", action="store_true", help="Only write chat-formatted JSONL")
    parser.add_argument("--train", action="store_true", help="Run local QLoRA training")
    parser.add_argument("--export-ollama", action="store_true", help="Write Ollama Modelfile + manifest")
    parser.add_argument("--stage", choices=["law_interpreter", "tag_generator"], default="law_interpreter")
    parser.add_argument("--splits-dir", default=str(_DEFAULT_DATA))
    parser.add_argument("--formatted-dir", default=str(_DEFAULT_FORMATTED))
    parser.add_argument("--adapter-dir", default=str(_DEFAULT_ADAPTERS))
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--print-colab", action="store_true", help="Print Colab/Kaggle instructions")
    args = parser.parse_args(argv)

    config = FinetuneConfig(
        stage=args.stage,
        epochs=args.epochs,
        formatted_dir=Path(args.formatted_dir),
        adapter_dir=Path(args.adapter_dir),
    )

    if args.format_only or args.train or (not args.print_colab and not args.export_ollama):
        written = format_splits(args.splits_dir, args.formatted_dir)
        print(f"Wrote {len(written)} formatted files to {args.formatted_dir}")

    if args.print_colab:
        print(colab_instructions(config))
        return 0

    if args.export_ollama:
        paths = export_ollama_artifacts(config)
        for name, path in paths.items():
            print(f"{name}: {path}")
        return 0

    if args.format_only:
        return 0

    if args.train:
        result = run_local_finetune(config)
        export_ollama_artifacts(config)
        print(
            f"Training complete ({result.backend}). adapter={result.adapter_dir} "
            f"train_loss={result.train_loss} eval_loss={result.eval_loss}"
        )
        print(f"Next: merge adapter → GGUF, then `ollama create {config.ollama_tag} -f ...`")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

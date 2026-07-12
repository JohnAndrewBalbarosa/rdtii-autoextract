#!/usr/bin/env bash
# Repeatable retrain cycle (Phases 1, 3, 4, 5) — backend/docs/TRAINING.md
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

PY="${PY:-.venv/bin/python}"
TRAIN_PY="${TRAIN_PY:-.venv-train/bin/python}"

echo "=== Phase 5: seed review log (optional) ==="
if [[ -f data/training/seed_review_decisions.json ]]; then
  "$PY" -m zetarix.pretrain.labeling.seed || true
fi

echo "=== Phase 1: rebuild datasets ==="
"$PY" -m zetarix.pretrain.dataset.build --docs-dir ../docs

echo "=== Phase 3: format chat JSONL ==="
"$PY" -m zetarix.pretrain.train.finetune --format-only

if [[ -x "$TRAIN_PY" ]] && "$TRAIN_PY" -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
  echo "=== Phase 3: QLoRA train (GPU) ==="
  "$TRAIN_PY" -m zetarix.pretrain.train.finetune --stage law_interpreter --train
  "$TRAIN_PY" -m zetarix.pretrain.train.finetune --stage tag_generator --train
else
  echo "=== Phase 3: skip train (no .venv-train GPU); use notebooks/finetune_colab.ipynb ==="
fi

echo "=== Phase 3: export Ollama manifests ==="
"$PY" -m zetarix.pretrain.train.finetune --export-ollama --stage law_interpreter
"$PY" -m zetarix.pretrain.train.finetune --export-ollama --stage tag_generator

echo "=== Phase 4: live eval (Ollama) ==="
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.1:latest}"
export OLLAMA_MODEL_LAW_INTERPRETER="${OLLAMA_MODEL_LAW_INTERPRETER:-zetarix-law-interpreter:latest}"
export OLLAMA_MODEL_TAG_GENERATOR="${OLLAMA_MODEL_TAG_GENERATOR:-zetarix-tag-generator:latest}"
"$PY" -m zetarix.pretrain.eval.harness --live

echo "=== Done ==="
echo "Reports: data/training/eval_report.json data/training/eval_report.md"

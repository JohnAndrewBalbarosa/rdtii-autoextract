# Training pipeline — dataset size, retrain cycle, and eval

See the full spec: [`pipeline-stages-and-training.md`](pipeline-stages-and-training.md).

## Package layout

Pre-training code is separated from runtime inference integration:

| Package | Purpose |
|---------|---------|
| `zetarix.pretrain` | Dataset build, labeling, QLoRA fine-tune, eval, review API |
| `zetarix.inference` | Few-shot grounding, indicator vocabulary, SetTrie at runtime |
| `zetarix.training` | Thin backward-compatible shims (old import paths still work) |

```
zetarix/pretrain/
  paths.py           # backend/data/training paths
  dataset/           # build.py, schemas.py, review_log.py
  labeling/          # ingest.py, seed.py
  train/             # finetune.py, export_ollama.py
  eval/              # harness.py, submission.py
  api/               # routes.py (review feedback)

zetarix/inference/
  grounding.py       # create_law_interpreter / create_tag_generator
  few_shot.py        # FewShotRetriever
  vocabulary.py      # constrained indicator tags
  set_trie.py        # SetTrie tag completion
  schemas.py         # LLM output JSON schemas
```

## Regenerate datasets (Phase 1)

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.dataset.build
# or: python -m zetarix.training.build_dataset  (shim)
```

Outputs under `backend/data/training/`:

| File | Purpose |
|------|---------|
| `law_interpreter_train.jsonl` | Law Interpreter examples (all) |
| `tag_generator_train.jsonl` | Tag Generator examples (all) |
| `splits/*_{train,val,test}.jsonl` | 80/10/10 stratified by jurisdiction + pillar |
| `dataset_report.txt` | Counts per stage / jurisdiction / pillar |

## Few-shot / RAG grounding (Phase 2)

Wired at inference via ``LawInterpreter`` and ``TagGenerator`` in ``zetarix/extraction/``.
The live ``ProvisionExtractor`` (``LLMProvisionExtractor``) chains both stages when
``ZETARIX_GROUNDING=few_shot`` (default) and training splits exist under
``backend/data/training/splits/``.

```bash
export ZETARIX_GROUNDING=few_shot   # or none for zero-shot
export ZETARIX_FEW_SHOT_K=3
export ZETARIX_LLM_BACKEND=local    # or remote / hybrid
```

```python
from zetarix.llm.router import LLMRouter
from zetarix.inference.grounding import create_law_interpreter, create_tag_generator

llm = LLMRouter.from_env()
interpreter = create_law_interpreter(llm)
tagger = create_tag_generator(llm)
```

Manual prompt building (for eval or custom pipelines):

```python
from zetarix.inference.few_shot import FewShotRetriever

retriever = FewShotRetriever.from_splits_dir("backend/data/training/splits")
prompt = retriever.build_law_interpreter_prompt(
    tagged_provision_input="...",
    jurisdiction="Singapore",
    pillar=6,
    k=3,
)
```

At inference, retrieved verified exemplars are injected before the LLM call. This is the
**primary path** when labeled data is below ~200–300 examples per stage.

## LoRA fine-tune (Phase 3)

### 1. Set up training venv (Python 3.10–3.13; not 3.14)

```bash
cd backend
python3.13 -m venv .venv-train
.venv-train/bin/pip install -r requirements-train.txt
# Optional faster path:
# .venv-train/bin/pip install "unsloth @ git+https://github.com/unslothai/unsloth.git"
```

### 2. Format + train (separate adapters per stage)

```bash
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.train.finetune --format-only

# Law Interpreter (rank 16, alpha 32, lr 2e-4, 3 epochs — tune on val loss)
PYTHONPATH=src .venv-train/bin/python -m zetarix.pretrain.train.finetune --stage law_interpreter --train

# Tag Generator (second adapter — do not merge tasks)
PYTHONPATH=src .venv-train/bin/python -m zetarix.pretrain.train.finetune --stage tag_generator --train
```

### 3. Export for Ollama

```bash
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.train.finetune --stage law_interpreter --export-ollama
# Merge adapter → GGUF (Unsloth save_pretrained_gguf or llama.cpp), then:
ollama create zetarix-law-interpreter:latest -f data/training/ollama/Modelfile.law_interpreter
ollama create zetarix-tag-generator:latest -f data/training/ollama/Modelfile.tag_generator
```

### 4. Point Zetarix at fine-tuned adapters

```bash
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL_LAW_INTERPRETER=zetarix-law-interpreter:latest
export OLLAMA_MODEL_TAG_GENERATOR=zetarix-tag-generator:latest
# fallback for non-stage calls:
export OLLAMA_MODEL=llama3.1:latest
```

`LocalLLMProvider` routes `agent_profile=law_interpreter` / `tag_generator` to the
stage-specific Ollama tags automatically.

### No local GPU?

Use `backend/notebooks/finetune_colab.ipynb` or:

```bash
PYTHONPATH=src python -m zetarix.pretrain.train.finetune --print-colab --stage law_interpreter
```

## Eval harness (Phase 4)

```bash
# Full live eval — all 27 test examples × 3 modes (requires Ollama):
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL=llama3.1:latest
export OLLAMA_MODEL_LAW_INTERPRETER=zetarix-law-interpreter:latest
export OLLAMA_MODEL_TAG_GENERATOR=zetarix-tag-generator:latest
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --live

# Quick smoke (5 examples):
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --live --max-examples 5

# Offline (oracle LLM, CI):
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --offline
```

Reports:
- `data/training/eval_report.json`
- `data/training/eval_report.md` (markdown table + per-jurisdiction breakdown)

Ship the fine-tuned adapter only if it beats few-shot/RAG by ≥0.05 F1 on Tag Generator;
otherwise keep `ZETARIX_GROUNDING=few_shot`.

## Review feedback loop (Phase 5)

Verify/reject in the review UI appends to `data/training/review_decisions.jsonl` when
`NEXT_PUBLIC_API_BASE_URL` points at the FastAPI backend:

```bash
# Start API
cd backend && PYTHONPATH=src .venv/bin/uvicorn zetarix.app.main:app --reload

# Frontend (.env.local)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Or POST directly:

```bash
curl -X POST http://localhost:8000/training/review-decision \
  -H 'Content-Type: application/json' \
  -d '{"id":"sg-pdpa-26","review_status":"verified","jurisdiction":"Singapore","pillar":6,"title":"...","scope":"...","provisions":"...","impact":"...","indicator":"6.2"}'
```

## Repeatable retrain cycle

```bash
cd backend && ./scripts/retrain_cycle.sh
```

Or step by step after reviewer sessions:

```bash
# 1. Verify/reject in UI → review_decisions.jsonl grows (auto-rebuild on each action when API is up)
# 2. Or seed from exported findings:
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.labeling.seed

# 3. Rebuild datasets + splits
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.dataset.build --docs-dir ../docs
# or: curl -X POST http://localhost:8000/training/rebuild-dataset

# 4. Check counts
curl http://localhost:8000/training/stats

# 5. Re-run eval
PYTHONPATH=src .venv/bin/python -m zetarix.pretrain.eval.harness --live
```

## Current eval results (live, llama3.1 + Ollama, n=32 test examples)

Full report: `data/training/eval_report.md` and `eval_report.json`.

| Mode | LI obligation acc | LI scope acc | TG P | TG R | TG F1 |
|------|-------------------|--------------|------|------|-------|
| zero_shot | 0.469 | 0.031 | 0.143 | 0.219 | **0.173** |
| few_shot/RAG | 0.750 | **0.969** | **0.438** | **0.438** | **0.438** |
| system_prompt_baseline* | 0.469 | 0.031 | 0.196 | 0.281 | 0.231 |

Prior baseline (n=27, spreadsheet-heavy labels): TG F1 **0.407**, LI scope **0.889**.

**After real-label ingest + constrained vocab:** TG F1 **0.438** (+0.031), LI scope **0.969** (+0.080).

\*System-prompt baseline used Modelfile-specialized `zetarix-*` models (system-prompt adapters on
`llama3.1:latest`), **not** true QLoRA weights — no LoRA adapters trained yet.

**Verdict:** Few-shot/RAG beats zero-shot by **+0.226 F1** on Tag Generator and lifts Law
Interpreter scope accuracy from 0.074 → 0.889. System-prompt baseline does **not** beat few-shot
(ΔF1 = −0.192). **Ship `ZETARIX_GROUNDING=few_shot` as the production path.**

## QLoRA gate (Priority 4)

Real QLoRA (`finetune.py --train`) is **not** attempted unless **both** conditions hold:

1. **300+** reviewer-verified examples with real provision text (not spreadsheet-proxy gold), and
2. Few-shot/RAG Tag Generator F1 has plateaued after label-quality + constrained-vocab fixes.

Until then, the system-prompt baseline slot in eval is for comparison only — never report it as
"fine-tuned" without the QLoRA caveat.

## Current dataset size

Run `build_dataset` to refresh. With only the golden workbooks (no review log), expect
~225 examples per stage across 10 jurisdictions. Focus jurisdictions (SG/AU/MY) have
~48 examples each — **below** the ~200–300 threshold for stable LoRA. More verified
review-UI labels unlock:

- Stable per-jurisdiction LoRA adapters
- Better few-shot retrieval pools for SG/AU/MY
- Reliable held-out eval on reviewer-confirmed (not spreadsheet-proxy) provision text

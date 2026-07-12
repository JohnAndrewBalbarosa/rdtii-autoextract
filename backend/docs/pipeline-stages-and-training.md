TASK: Build the training data pipeline and LoRA fine-tuning workflow for the Law 
Interpreter and Law-Aware Tag Generator stages, using the existing golden dataset and 
review-UI-verified findings as source labels.

CONTEXT:
- HTML Structure Tagger stays rule-based (BeautifulSoup scaffolds) — do NOT fine-tune 
  anything for this stage. Its LLM fallback (for unknown layouts) can stay on few-shot 
  prompting; it doesn't have enough labeled examples to justify a fine-tune and isn't 
  the bottleneck.
- Fine-tuning target is the Law Interpreter and Tag Generator stages only, since those 
  are the two doing legal reasoning and RDTII-specific classification — the parts most 
  worth specializing.
- Base model: Llama 3.x via Ollama (already the documented open-weight target in 
  backend/docs/ARCHITECTURE.md). Use the instruct variant closest in size to what 
  Ollama already runs on the dev machine (8B unless otherwise specified).
- Golden dataset + review UI verify/reject actions are the label source. Treat "verified" 
  Findings as positive examples and "rejected" ones as hard negatives — don't throw the 
  rejects away, they're useful signal for what NOT to output.

PHASE 1 — DATA PIPELINE (do this first, before touching any training code)

1. Build an extraction script (backend/src/zetarix/training/build_dataset.py) that walks 
   the golden dataset + any review-UI-logged verify/reject decisions and emits two JSONL 
   files:
   - law_interpreter_train.jsonl — records of {tagged_provision_input, jurisdiction, 
     pillar} -> {obligation_type, scope, applicability_triggers, plain_summary}
   - tag_generator_train.jsonl — records of {legal_interpretation, jurisdiction, pillar, 
     precedent_tags} -> {indicator_tags: [...], rationale}
2. Report the actual example count per pillar/jurisdiction before doing anything else. 
   If total labeled examples are under ~200-300 per stage, say so explicitly — that's 
   too small for a stable LoRA fine-tune and the right call is to lean harder on 
   few-shot/RAG grounding instead (see Phase 2) and treat fine-tuning as a stretch goal, 
   not the primary path.
3. Split train/val/test (e.g. 80/10/10), stratified by jurisdiction and pillar so SG/AU/MY 
   are all represented in each split, not just dumped into train.

PHASE 2 — BASELINE (build this regardless of whether fine-tuning happens)

1. Implement few-shot/RAG grounding for both stages: at inference time, retrieve the 
   k most similar prior verified examples (same jurisdiction + pillar, nearest by the 
   existing SetTrieIndex or a simple embedding similarity) and inject them into the 
   prompt as exemplars before calling the LLM.
2. This is the fallback path if the fine-tune underperforms or the dataset turns out 
   too small — and it's also the tool used to generate the eval baseline in Phase 4, 
   so build it first.

PHASE 3 — LORA FINE-TUNE

1. Tooling: use Unsloth or Axolotl (whichever the agent finds cleaner to set up against 
   the available compute) with 4-bit QLoRA — don't attempt full fine-tuning, it's not 
   necessary and not affordable on this hardware.
2. Format law_interpreter_train.jsonl and tag_generator_train.jsonl into the chat/instruct 
   template the base model expects. Keep the two stages as separate fine-tunes (or 
   separate LoRA adapters on the same base model) — don't merge them into one task, 
   they have different input/output shapes and merging will blur both.
3. Starting hyperparameters: rank 16, alpha 32, learning rate ~2e-4, 2-3 epochs — flag 
   these as a starting point to tune against val loss, not fixed values.
4. After training, merge/export the LoRA adapter and convert to GGUF so it can be loaded 
   into Ollama as a custom model tag (e.g. `zetarix-law-interpreter:latest`), then point 
   ZETARIX_LLM_BACKEND=local at it via the LLMRouter config.
5. If compute isn't available locally, document the exact Colab/Kaggle notebook steps 
   needed to train remotely and pull the resulting adapter back down — don't silently 
   skip this phase.

PHASE 4 — EVAL HARNESS (extend, don't duplicate, the existing scoring/ module)

1. Add precision/recall/F1 computation per stage against the held-out test split — this 
   is the metric the README already flags as missing. Score:
   - Law Interpreter: obligation-type classification accuracy + scope classification accuracy
   - Tag Generator: indicator-tag precision/recall against ground-truth tags per finding
2. Run the eval three ways and report all three side by side: (a) zero-shot base model, 
   (b) few-shot/RAG-grounded base model, (c) fine-tuned model. This tells you honestly 
   whether the fine-tune was worth the compute — don't skip (a) and (b) just because (c) 
   is the "real" deliverable.
3. If the fine-tuned model doesn't beat the RAG-grounded baseline by a meaningful margin, 
   say so plainly rather than shipping it anyway.

PHASE 5 — FEEDBACK LOOP

1. Wire the review UI's verify/reject actions to append to the training JSONL files 
   automatically (not just to the golden dataset used for gold-mode output), so every 
   human review session grows the training set for the next fine-tune pass.
2. Document how to re-run Phases 1, 3, and 4 as a repeatable retrain cycle, not a one-off script.

DELIVERABLES:
- backend/src/zetarix/training/ module: build_dataset.py, few_shot_retriever.py, 
  finetune.py (or equivalent scripts), eval_harness.py
- Two JSONL datasets + train/val/test splits committed or documented (don't commit large 
  binaries — document the regeneration command instead)
- Eval report comparing zero-shot / few-shot / fine-tuned, with actual numbers, not just 
  "it works"
- Updated docs/ note on dataset size, what it currently supports, and what more labeled 
  data would unlock

REPORT BACK EXPLICITLY:
- How many labeled examples were available per stage/pillar/jurisdiction
- Whether that was enough to justify the fine-tune, and why
- The precision/recall/F1 numbers for all three eval conditions
- Whether ZETARIX_LLM_BACKEND=local now serves the fine-tuned adapter successfully
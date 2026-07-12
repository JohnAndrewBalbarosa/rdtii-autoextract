# Training eval report (Phase 4)

Metrics computed on held-out test split (stratified 80/10/10).
Law Interpreter: obligation-type + scope classification accuracy.
Tag Generator: micro-averaged precision/recall/F1 over indicator tags per finding.
System-prompt baseline slot uses Ollama Modelfile-specialized adapters (zetarix-law-interpreter:latest) — NOT true QLoRA weights. Replace with QLoRA GGUF when adapters are trained.

## Test split size

| Stage | Examples |
|-------|----------|
| Law Interpreter | 32 |
| Tag Generator | 32 |

## Results (all three conditions)

| Mode | LI obligation acc | LI scope acc | TG precision | TG recall | TG F1 |
|------|-------------------|--------------|--------------|-----------|-------|
| zero_shot | 0.469 | 0.031 | 0.143 | 0.219 | 0.173 |
| few_shot | 0.750 | 0.969 | 0.438 | 0.438 | 0.438 |
| system_prompt_baseline | 0.469 | 0.031 | 0.196 | 0.281 | 0.231 |

## Verdict

Few-shot/RAG vs zero-shot: Tag Generator F1 delta = +0.265 (0.438 vs 0.173). System-prompt baseline does NOT beat few-shot/RAG by a meaningful margin (delta F1=-0.207). Prefer the RAG-grounded baseline. Law Interpreter obligation accuracy: few-shot 0.750 vs zero-shot 0.469 (delta +0.281).

### Law Interpreter by jurisdiction (zero_shot)

- **Australia**: obligation=0.000 scope=0.000
- **China**: obligation=0.667 scope=0.000
- **India**: obligation=0.500 scope=0.250
- **Indonesia**: obligation=0.667 scope=0.000
- **Lao PDR**: obligation=1.000 scope=0.000
- **Malaysia**: obligation=0.200 scope=0.000
- **Mongolia**: obligation=0.500 scope=0.000
- **Russian Federation**: obligation=1.000 scope=0.000
- **Singapore**: obligation=0.000 scope=0.000
- **Thailand**: obligation=0.750 scope=0.000

### Tag Generator by jurisdiction (zero_shot)

- **Australia**: P=0.200 R=0.333 F1=0.250
- **China**: P=0.250 R=0.333 F1=0.286
- **India**: P=0.143 R=0.250 F1=0.182
- **Indonesia**: P=0.167 R=0.333 F1=0.222
- **Lao PDR**: P=0.000 R=0.000 F1=0.000
- **Malaysia**: P=0.143 R=0.200 F1=0.167
- **Mongolia**: P=0.333 R=0.500 F1=0.400
- **Russian Federation**: P=0.000 R=0.000 F1=0.000
- **Singapore**: P=0.000 R=0.000 F1=0.000
- **Thailand**: P=0.143 R=0.250 F1=0.182

### Law Interpreter by jurisdiction (few_shot)

- **Australia**: obligation=0.667 scope=1.000
- **China**: obligation=0.667 scope=1.000
- **India**: obligation=0.750 scope=1.000
- **Indonesia**: obligation=0.667 scope=1.000
- **Lao PDR**: obligation=1.000 scope=1.000
- **Malaysia**: obligation=0.800 scope=0.800
- **Mongolia**: obligation=0.500 scope=1.000
- **Russian Federation**: obligation=1.000 scope=1.000
- **Singapore**: obligation=0.750 scope=1.000
- **Thailand**: obligation=0.750 scope=1.000

### Tag Generator by jurisdiction (few_shot)

- **Australia**: P=0.333 R=0.333 F1=0.333
- **China**: P=0.667 R=0.667 F1=0.667
- **India**: P=0.750 R=0.750 F1=0.750
- **Indonesia**: P=0.333 R=0.333 F1=0.333
- **Lao PDR**: P=0.000 R=0.000 F1=0.000
- **Malaysia**: P=0.200 R=0.200 F1=0.200
- **Mongolia**: P=0.500 R=0.500 F1=0.500
- **Russian Federation**: P=0.500 R=0.500 F1=0.500
- **Singapore**: P=0.750 R=0.750 F1=0.750
- **Thailand**: P=0.250 R=0.250 F1=0.250

### Law Interpreter by jurisdiction (system_prompt_baseline)

- **Australia**: obligation=0.000 scope=0.000
- **China**: obligation=0.667 scope=0.000
- **India**: obligation=0.500 scope=0.250
- **Indonesia**: obligation=0.667 scope=0.000
- **Lao PDR**: obligation=1.000 scope=0.000
- **Malaysia**: obligation=0.200 scope=0.000
- **Mongolia**: obligation=0.500 scope=0.000
- **Russian Federation**: obligation=1.000 scope=0.000
- **Singapore**: obligation=0.000 scope=0.000
- **Thailand**: obligation=0.750 scope=0.000

### Tag Generator by jurisdiction (system_prompt_baseline)

- **Australia**: P=0.250 R=0.333 F1=0.286
- **China**: P=0.250 R=0.333 F1=0.286
- **India**: P=0.143 R=0.250 F1=0.182
- **Indonesia**: P=0.333 R=0.667 F1=0.444
- **Lao PDR**: P=0.000 R=0.000 F1=0.000
- **Malaysia**: P=0.167 R=0.200 F1=0.182
- **Mongolia**: P=0.667 R=1.000 F1=0.800
- **Russian Federation**: P=0.000 R=0.000 F1=0.000
- **Singapore**: P=0.000 R=0.000 F1=0.000
- **Thailand**: P=0.143 R=0.250 F1=0.182

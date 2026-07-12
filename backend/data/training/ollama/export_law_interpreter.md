# Export law_interpreter adapter to Ollama

## Prerequisites
- LoRA adapter at `/home/ken/rdtii-autoextract/backend/data/training/adapters/law_interpreter/`
- Base weights: `llama3.1:latest` (Ollama) or HuggingFace `meta-llama/Meta-Llama-3-8B-Instruct`

## Option A — Unsloth (recommended)
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="/home/ken/rdtii-autoextract/backend/data/training/adapters/law_interpreter",
    max_seq_length=2048,
    load_in_4bit=True,
)
model.save_pretrained_gguf("/home/ken/rdtii-autoextract/backend/data/training/ollama/law_interpreter", tokenizer, quantization_method="q4_k_m")
```

## Option B — llama.cpp
```bash
# 1. Merge LoRA into base (Python peft merge_and_unload or unsloth)
# 2. Convert to GGUF:
python -m llama_cpp.convert_hf_to_gguf merged-law_interpreter/ --outfile /home/ken/rdtii-autoextract/backend/data/training/ollama/law_interpreter.gguf
```

## Create Ollama model
```bash
ollama create zetarix-law_interpreter:latest -f /home/ken/rdtii-autoextract/backend/data/training/ollama/Modelfile.law_interpreter
```

## Point Zetarix at the adapter
```bash
export ZETARIX_LLM_BACKEND=local
export OLLAMA_MODEL_LAW_INTERPRETER=zetarix-law_interpreter:latest
# or single model fallback:
export OLLAMA_MODEL=zetarix-law_interpreter:latest
```

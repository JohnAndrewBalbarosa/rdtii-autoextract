# rdtii-autoextract

## Overview

RDTII AutoExtract — open-source, model-agnostic AI pipeline automating ~80% of the UN ESCAP RDTII digital-trade regulatory workflow. Apache 2.0.

Repository: [JohnAndrewBalbarosa/rdtii-autoextract](https://github.com/JohnAndrewBalbarosa/rdtii-autoextract)

## Problem and Goal

This project should be read as a technical build: it identifies a concrete workflow or research problem, implements a working system around that problem, and documents enough evidence for another person to understand, run, and evaluate the result.

Primary goals:

- Explain what the project does and who it is for.
- Show the architecture and implementation choices.
- Provide enough setup guidance for local review.
- Report measured results when available.
- Make limitations and next steps explicit instead of implying unverified impact.

## System Design

Current documented components:

- Frontend application or user interface layer.
- Backend service, API, or domain layer.
- Documentation folder for architecture, requirements, or supporting notes.

Project tags:

- To be tagged based on the final project stack.

## Setup and Usage

Use the commands below as the starting point for local setup. Verify environment variables, secrets, datasets, and external services before running production-like workflows.

```bash
cd frontend
npm install
npm run dev
cd ..
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Evaluation Method

- Designed the pipeline around the UN ESCAP RDTII digital-trade regulatory workflow.
- Separated the workflow into discover, OCR/captioning, tag/extract, human review, and concept-graph stages.
- Kept AI providers behind ports and adapters so model choices can be swapped without rewriting the domain layer.

## Results

- Current project claim: automates about 80% of the discover-to-describe workflow while keeping the final 20% for transparent human review.
- Token benchmark evidence is saved under `backend/benchmarks/results/`.
- On the `inspect_au` fixture, deterministic cleaning reduced raw HTML from 77,125 tokens to 9,743 cleaned-text tokens, an 87.4% reduction.
- On the `walkthrough_au` fixture, deterministic cleaning reduced raw HTML from 103,171 tokens to 9,743 cleaned-text tokens, a 90.6% reduction.
- Structural skeleton prompts reduced the same fixtures by 88.1% and 91.1%, respectively, while preserving layout signals for selector learning.
- The pipeline learned each page layout once, then reused cached layout rules so same-layout per-page extraction used 0 additional LLM tokens.
- At 100 pages, the saved model reports 773.6x fewer application LLM tokens than a naive raw-HTML-per-page agent baseline on `inspect_au`; this multiplier is baseline-dependent, not a provider-billing measurement.
- Deterministic quality checks reported 100.0% fingerprint stability across seven noise variants per fixture and no detected boilerplate contamination.
- Measured extraction accuracy, reviewer agreement, latency, and jurisdiction-level coverage are not yet published in the README.

## Interpretation

- The repository has a clear automation target and architecture, but still needs benchmark evidence before the 80/20 split can be treated as a validated result.
- The token-saving mechanism has stronger evidence than the end-to-end RDTII extraction quality claim: compression, layout caching, and zero-token same-layout extraction are backed by saved benchmark artifacts.
- The headline multiplier should be presented as a comparison against a naive agent baseline that re-ingests raw HTML per page; a smarter cached agent would reduce the gap.

## Limitations

- Results should only be treated as validated when this README includes the dataset, sample size, metric definition, and reproduction steps.
- Any AI-generated, OCR-based, scraped, or heuristic output requires manual review before being used as ground truth.
- Environment-dependent measurements such as latency, memory use, browser behavior, and API reliability should be re-measured on the target machine.

## Recommendations and Future Work

- Create a gold-label sample of RDTII documents and report field-level precision, recall, and F1.
- Measure reviewer time saved before and after AI suggestions.
- Report failure modes by document type, jurisdiction, language, and OCR quality.
- Add provider-level tracing for real input/output token billing during a live multi-page crawl.

## Documentation Standard

This README follows a technical-project structure: overview, goal, system design, setup, evaluation method, results, interpretation, limitations, and recommendations. Update the Results section whenever new measurements are available so project claims stay evidence-backed.

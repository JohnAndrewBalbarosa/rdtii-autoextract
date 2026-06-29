"""Knowledge Distillation pipeline for Qwen.

This script acts as the "Teacher-Student" coordinator. It uses the high-reasoning
remote model (Gemini/Claude) as the Teacher to generate high-quality, structured training
examples from raw legal text. These examples are saved in a standardized ChatML JSONL dataset
ready for fine-tuning the local student model (Qwen).

Workflow:
1. Load seed URLs / legal texts.
2. Crawl and clean the documents.
3. Call the Remote LLM (Teacher) to perform extraction and structuring.
4. Record the raw inputs (system instructions, user prompts) and the high-fidelity outputs.
5. Format and save as a dataset compatible with Qwen fine-tuning (e.g. LLaMA-Factory / SFT).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.llm.remote_provider import RemoteLLMProvider, prepare_prompt
from adapters.botting.l4_transport.playwright_client import PlaywrightClient
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.l7_application.pipeline_adapter import PipelineAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--urls",
        nargs="+",
        default=[
            "https://www.w3.org/Consortium/Legal/2002/copyright-documents-20021231",
            "file:///home/ken/rdtii-autoextract/backend/test_law.html"
        ],
        help="List of URLs to process for distillation.",
    )
    parser.add_argument(
        "--output-file",
        default="qwen_distillation_dataset.jsonl",
        help="Where to save the distilled ChatML training dataset.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" ZETARIX KNOWLEDGE DISTILLATION PIPELINE (Teacher: Gemini -> Student: Qwen)")
    print("=" * 60)

    # Initialize Gemini as the high-reasoning Teacher
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("[ERROR] GEMINI_API_KEY is not set. A remote key is required for the Teacher model.")
        sys.exit(1)

    model_name = os.environ.get("REMOTE_LLM_MODEL") or "gemini-2.5-flash"
    teacher = RemoteLLMProvider(model=model_name, api_key=gemini_key)
    print(f"Teacher Model: {model_name}")
    print(f"Output File:   {os.path.abspath(args.output_file)}")
    print("-" * 60)

    # Crawler setup
    print("Initializing Playwright browser...")
    fetcher = PlaywrightClient(headless=True)
    cleaner = DomCleaner()
    registry = ScaffoldRegistry([])
    
    # Schemas
    extraction_schema = {"type": "object", "properties": {"markdown_content": {"type": "string"}}}
    structuring_schema = {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "level": {"type": "integer"},
                        "text": {"type": "string"},
                    },
                    "required": ["heading", "level", "text"],
                },
            }
        },
        "required": ["sections"],
    }

    records_written = 0

    with open(args.output_file, "w", encoding="utf-8") as out_f:
        for idx, url in enumerate(args.urls):
            print(f"\n[{idx+1}/{len(args.urls)}] Fetching: {url}")
            try:
                if url.startswith("file://"):
                    path = url.replace("file://", "")
                    with open(path, "r", encoding="utf-8") as f:
                        html = f.read()
                else:
                    html = fetcher.fetch(url)
                
                cleaned_text = cleaner.clean_html(html)
                if not cleaned_text.strip():
                    print("  Skipping: cleaned text is empty.")
                    continue

                # -------------------------------------------------------------
                # Task 1: Extraction Distillation
                # -------------------------------------------------------------
                print("  Generating Extraction Task...")
                extraction_system = "You are a legal assistant. Extract all legal sections from the text. Remove conversational fluff and return raw Markdown chunks."
                extraction_prompt = f"Text to extract:\n\n{cleaned_text}"
                
                # Get Teacher output
                extracted_res = teacher.complete(
                    prompt=prepare_prompt(extraction_prompt, extraction_schema),
                    schema=extraction_schema,
                    agent_profile="extraction_agent"
                )
                
                # Format into ChatML for Qwen fine-tuning
                extraction_train_instance = {
                    "messages": [
                        {"role": "system", "content": extraction_system},
                        {"role": "user", "content": extraction_prompt},
                        {"role": "assistant", "content": json.dumps(extracted_res, ensure_ascii=False)}
                    ]
                }
                out_f.write(json.dumps(extraction_train_instance, ensure_ascii=False) + "\n")
                records_written += 1

                # -------------------------------------------------------------
                # Task 2: Structuring Distillation
                # -------------------------------------------------------------
                markdown_text = extracted_res.get("markdown_content", "")
                if markdown_text.strip():
                    print("  Generating Structuring Task...")
                    structuring_system = "Format the markdown content into a structured JSON object containing a list of 'sections' with heading, level, and text."
                    structuring_prompt = f"Markdown content:\n\n{markdown_text}"
                    
                    # Get Teacher output
                    structured_res = teacher.complete(
                        prompt=prepare_prompt(structuring_prompt, structuring_schema),
                        schema=structuring_schema,
                        agent_profile="structuring_agent"
                    )
                    
                    # Format into ChatML for Qwen fine-tuning
                    structuring_train_instance = {
                        "messages": [
                            {"role": "system", "content": structuring_system},
                            {"role": "user", "content": structuring_prompt},
                            {"role": "assistant", "content": json.dumps(structured_res, ensure_ascii=False)}
                        ]
                    }
                    out_f.write(json.dumps(structuring_train_instance, ensure_ascii=False) + "\n")
                    records_written += 1

            except Exception as e:
                print(f"  [ERROR] Failed during distillation for {url}: {e}")

    print("-" * 60)
    print(f"[COMPLETED] Knowledge Distillation finished. Wrote {records_written} training records to {args.output_file}")
    print("You can now feed this JSONL file to LLaMA-Factory, Unsloth, or Axolotl to fine-tune your local Qwen model!")
    print("=" * 60)


if __name__ == "__main__":
    main()

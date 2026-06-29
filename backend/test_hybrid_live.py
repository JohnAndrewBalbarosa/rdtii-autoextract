"""End-to-end integration test script for hybrid LLM routing.

Loads the LLMRouter from the environment/dotenv file, instantiates the pipeline
and orchestrator, and attempts to scrape and validate a URL.
Uses PlaywrightClient to support JS rendering for dynamic legal portals.

Run with:
    python test_hybrid_live.py --url <URL>
"""

from __future__ import annotations

import argparse
import sys
import os
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.llm.router import LLMRouter
from adapters.botting.l4_transport.playwright_client import PlaywrightClient
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.l7_application.pipeline_adapter import PipelineAdapter
from core.pipeline.document_validator import DocumentComplianceValidator
from core.pipeline.scraper_orchestrator import ScraperOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="https://sso.agc.gov.sg/Act/PDPA2012",
        help="The URL to scrape and validate.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" ZETARIX HYBRID LLM ROUTING TESTER")
    print("=" * 60)

    # Initialize router
    router = LLMRouter.from_env()
    print(f"Active Backend: {router._backend}")
    
    # Remote provider configuration
    remote_provider = router._providers["remote"]
    print(f"Remote Model:   {remote_provider._model}")
    print(f"Gemini Key:     {'[SET]' if os.environ.get('GEMINI_API_KEY') else '[NOT SET]'}")
    print(f"Anthropic Key:  {'[SET]' if os.environ.get('ANTHROPIC_API_KEY') else '[NOT SET]'}")
    print(f"OpenAI Key:     {'[SET]' if os.environ.get('OPENAI_API_KEY') else '[NOT SET]'}")
    
    # Local provider configuration
    local_provider = router._providers["local"]
    print(f"Local Model:    {local_provider._model}")
    print(f"Ollama Host:    {local_provider._endpoint}")
    print("-" * 60)

    # Local storage to capture all intermediate agent steps
    agent_outputs = {}
    scraping_details = {}

    # Intercept complete calls for full debugging visibility
    original_complete = router.complete
    def debug_complete(prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        print(f"\n[INTERCEPT] Agent Profile: '{agent_profile}' calling...")
        print(f"  Prompt size: {len(prompt)} chars")
        print(f"  Prompt snippet:\n{prompt[:350]}\n  ...")
        try:
            res = original_complete(prompt, schema, agent_profile)
            agent_outputs[agent_profile] = {
                "prompt": prompt,
                "schema": schema,
                "response": res
            }
            print(f"  Response: (valid JSON conforms to schema)")
            print(f"  Response snippet:\n{json.dumps(res, indent=2)[:350]}\n  ...")
            return res
        except Exception as e:
            agent_outputs[agent_profile] = {
                "prompt": prompt,
                "schema": schema,
                "error": str(e)
            }
            print(f"  Response failed: {e}")
            raise

    router.complete = debug_complete

    # Initialize components
    print("Initializing Playwright browser...")
    fetcher = PlaywrightClient(headless=True)
    cleaner = DomCleaner()
    
    # Intercept cleaner to capture raw HTML, selectors and cleaned output text
    original_clean = cleaner.clean_html
    def debug_clean_html(html_content: str, selectors: dict[str, str] = None) -> str:
        scraping_details["raw_html"] = html_content
        scraping_details["selectors_used"] = selectors
        result = original_clean(html_content, selectors)
        scraping_details["cleaned_text"] = result
        return result
    cleaner.clean_html = debug_clean_html

    registry = ScaffoldRegistry([])  # empty registry is fine for fallback scraping
    
    pipeline = PipelineAdapter(
        llm_provider=router,
        fetcher=fetcher,
        cleaner=cleaner,
        scaffold_registry=registry,
    )
    validator = DocumentComplianceValidator(llm_provider=router)
    orchestrator = ScraperOrchestrator(extractor=pipeline, validator=validator)

    print(f"Scraping and validating URL: {args.url}")
    print("This will call Ollama for extraction/structuring, then Gemini for validation...")
    print("-" * 60)
    
    try:
        results = orchestrator.scrape_and_validate([args.url])
        
        # Save full agent trace/audit trail to a file (saves on both success and rejection/failure)
        output_data = {
            "document_url": args.url,
            "validation_passed": len(results) > 0,
            "scraping_audit_trail": {
                "selectors_used": scraping_details.get("selectors_used"),
                "raw_html": scraping_details.get("raw_html", ""),
                "cleaned_text": scraping_details.get("cleaned_text", "")
            },
            "agent_audit_trail": {
                "extraction_agent": agent_outputs.get("extraction_agent"),
                "structuring_agent": agent_outputs.get("structuring_agent"),
                "validation_agent": agent_outputs.get("main_controller")
            }
        }
        
        output_file = "extracted_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        print(f"\nSaved full agent audit trail to: {os.path.abspath(output_file)}")
        print("-" * 60)
        
        if results:
            print("[SUCCESS] Document parsed and validated successfully!")
            doc = results[0]
            print(f"URL: {doc.document_url}")
            print(f"Language: {doc.language}")
            print(f"Sections extracted: {len(doc.sections)}")
            for i, sec in enumerate(doc.sections[:3]):
                print(f"  Section {i+1}: {sec.heading} (Level {sec.level})")
                print(f"    Text: {sec.text[:120]}...")
            if len(doc.sections) > 3:
                print(f"  ... and {len(doc.sections) - 3} more sections.")
        else:
            print("[REJECTED] The document was parsed but marked as INVALID by the validation agent.")
            
    except NotImplementedError as e:
        print(f"\n[OFFLINE FALLBACK TRIGGERED] Provider raised NotImplementedError:\n{e}")
        print("This is expected if your Ollama instance is offline or Gemini API keys are missing/invalid.")
    except RuntimeError as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
            print("\n[PLAYWRIGHT ERROR] Playwright browsers are not installed. Run: playwright install")
        else:
            print(f"\n[ERROR] Playwright runtime error:\n{e}")
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed:\n{e}")


if __name__ == "__main__":
    main()

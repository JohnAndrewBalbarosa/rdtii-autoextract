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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from zetarix.llm.router import LLMRouter
from zetarix.transport.playwright_client import PlaywrightClient
from zetarix.cleaning.dom_cleaner import DomCleaner
from zetarix.scaffolds.scaffold_registry import ScaffoldRegistry
from zetarix.crawling.pipeline_adapter import PipelineAdapter
from zetarix.validation.document_validator import DocumentComplianceValidator
from zetarix.orchestration.scraper_orchestrator import ScraperOrchestrator


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

    # Intercept complete calls for full debugging visibility
    original_complete = router.complete
    def debug_complete(prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        print(f"\n[INTERCEPT] Agent Profile: '{agent_profile}' calling...")
        print(f"  Prompt size: {len(prompt)} chars")
        print(f"  Prompt snippet:\n{prompt[:350]}\n  ...")
        try:
            res = original_complete(prompt, schema, agent_profile)
            print(f"  Response: (valid JSON conforms to schema)")
            print(f"  Response snippet:\n{json.dumps(res, indent=2)[:350]}\n  ...")
            return res
        except Exception as e:
            print(f"  Response failed: {e}")
            raise

    router.complete = debug_complete

    # Initialize components
    print("Initializing Playwright browser...")
    fetcher = PlaywrightClient(headless=True)
    cleaner = DomCleaner()
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
        if results:
            print("\n[SUCCESS] Document parsed and validated successfully!")
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
            print("\n[REJECTED] The document was parsed but marked as INVALID by the remote Gemini validator agent.")
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

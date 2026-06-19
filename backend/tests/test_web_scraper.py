from core.ports import LLMProvider, HtmlFetcherPort
from adapters.botting.l4_transport.factory import TransportFactory
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.scaffolds.homeaffairs_gov_au import HomeAffairsScaffold
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.l7_application.pipeline_adapter import PipelineAdapter
from core.pipeline.scraper_orchestrator import ScraperOrchestrator
from core.pipeline.document_validator import DocumentComplianceValidator

class MockLLMProvider(LLMProvider):
    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "extraction_agent":
            return {"markdown_content": "# Mock Heading\n\nThis is a mock clause."}
        elif agent_profile == "structuring_agent":
            return {"sections": [{"heading": "Mock Heading", "level": 1, "text": "This is a mock clause."}]}
        elif agent_profile == "main_controller":
            return {"is_valid": True}
        return {}

class MockStaticFetcher(HtmlFetcherPort):
    def fetch(self, url: str) -> str:
        if "dynamic" in url:
            return "<html><body>Enable JavaScript to view this page</body></html>"
        return "<html><main><h1>Static Law</h1><p>Content</p></main></html>"

class MockDynamicFetcher(HtmlFetcherPort):
    def fetch(self, url: str) -> str:
        return "<html><main><h1>Dynamic Law</h1><p>Rendered Content</p></main></html>"

def test_transport_factory_switching():
    static = MockStaticFetcher()
    dynamic = MockDynamicFetcher()
    factory = TransportFactory(static, dynamic)
    
    # Test static content
    content_static = factory.fetch("http://static.com")
    assert "Static Law" in content_static
    
    # Test automatic fallback to dynamic
    content_dynamic = factory.fetch("http://dynamic.com")
    assert "Dynamic Law" in content_dynamic

def test_pipeline_with_scaffold_registry():
    llm = MockLLMProvider()
    static = MockStaticFetcher()
    dynamic = MockDynamicFetcher()
    factory = TransportFactory(static, dynamic)
    cleaner = DomCleaner()
    
    scaffold = HomeAffairsScaffold()
    registry = ScaffoldRegistry([scaffold])
    
    pipeline = PipelineAdapter(llm, factory, cleaner, registry)
    
    # Test matching scaffold
    doc = pipeline.scrape_url("https://www.homeaffairs.gov.au/test")
    assert doc.document_url == "https://www.homeaffairs.gov.au/test"
    assert len(doc.sections) == 1
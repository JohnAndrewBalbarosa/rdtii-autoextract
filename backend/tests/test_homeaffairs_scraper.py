import pytest
from core.ports import LLMProvider, HtmlFetcherPort
from adapters.botting.l4_transport.factory import TransportFactory
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.scaffolds.homeaffairs_gov_au import HomeAffairsScaffold
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.l7_application.pipeline_adapter import PipelineAdapter

class MockLLMProvider(LLMProvider):
    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "extraction_agent":
            return {"markdown_content": "# Legal Section\n\nThis is a legislative reforms."}
        elif agent_profile == "structuring_agent":
            return {"sections": [{"heading": "Legal Section", "level": 1, "text": "This is a legislative reforms."}]}
        return {}

class MockHomeAffairsFetcher(HtmlFetcherPort):
    def fetch(self, url: str) -> str:
        return """
        <html>
            <body>
                <main id="content">
                    <h1>2023-2030 Australian Cyber Security Strategy</h1>
                    <p>This strategy outlines legislative reforms and new regulatory frameworks.</p>
                    <a href="/documents/strategy.pdf">Download Strategy PDF</a>
                    <a href="/news/latest-updates">Latest Updates</a>
                </main>
                <footer>
                    <a href="/contact">Contact Us</a>
                </footer>
            </body>
        </html>
        """

def test_homeaffairs_legal_framework_discovery():
    llm = MockLLMProvider()
    fetcher = MockHomeAffairsFetcher()
    cleaner = DomCleaner()
    
    scaffold = HomeAffairsScaffold()
    registry = ScaffoldRegistry([scaffold])
    
    pipeline = PipelineAdapter(llm, fetcher, cleaner, registry)
    
    url = "https://www.homeaffairs.gov.au/cyber-security-subsite/Pages/2023-2030-australian-cyber-security-strategy.aspx"
    doc = pipeline.scrape_url(url)
    
    # 1. Verify custom selectors were used (content restricted to main#content)
    # The 'Contact Us' link in footer should NOT be in article_links if we use the right selector
    discovered_links = doc.metadata.get("discovered_links", {})
    assert "/documents/strategy.pdf" in discovered_links.get("pdf_links", [])
    assert "/news/latest-updates" in discovered_links.get("article_links", [])
    assert "/contact" not in discovered_links.get("article_links", [])
    
    # 2. Verify keyword-based relevance tagging
    assert "legal-priority" in doc.tags
    
    # 3. Verify cleaned text contains the keywords that triggered the tag
    # 'legislative reforms' or 'regulatory frameworks' are in the mock HTML
    assert "legislative reforms" in doc.sections[0].text.lower() or any("legislative reforms" in s.text.lower() for s in doc.sections)

if __name__ == "__main__":
    pytest.main([__file__])

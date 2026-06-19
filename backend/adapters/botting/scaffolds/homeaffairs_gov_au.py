from .base_scaffold import BaseScaffold

class HomeAffairsScaffold(BaseScaffold):
    """Scaffold for the Australian Department of Home Affairs."""

    @property
    def target_domain(self) -> str:
        return "homeaffairs.gov.au"

    def get_transport_type(self) -> str:
        # Home Affairs often uses dynamic components, but some pages are static.
        # We'll stick to 'auto' to allow the factory to decide.
        return "auto"

    def get_custom_selectors(self) -> dict[str, str]:
        return {
            "content_area": "main, #content, article",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a',
            "title": "h1",
            "sections": "h2, h3, p"
        }

    def get_keywords(self) -> list[str]:
        return [
            "law", "legislation", "framework", "legal", "act", 
            "regulation", "regulatory frameworks", "Cyber Security Act", 
            "legislative reforms"
        ]

from .base_scaffold import BaseScaffold

class PDPCScaffold(BaseScaffold):
    """Scaffold for Singapore Personal Data Protection Commission (pdpc.gov.sg)."""

    @property
    def target_domain(self) -> str:
        return "pdpc.gov.sg"

    def get_transport_type(self) -> str:
        # PDPC pages are typically static, but some may have interactive elements.
        return "auto"

    def get_custom_selectors(self) -> dict[str, str]:
        return {
            "content_area": ".page-content, main, #content, article",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a, article a',
            "title": "h1, .page-title",
            "sections": "h2, h3, p, .guidance-section",
        }

    def get_boilerplate_selectors(self) -> list[str]:
        return [".breadcrumb", ".related-content", ".share-bar", ".sidebar", ".footer"]

    def get_keywords(self) -> list[str]:
        return [
            "data protection", "privacy", "pdpa", "personal data",
            "guidance", "framework", "regulation", "compliance",
            "singapore", "commissioner"
        ]

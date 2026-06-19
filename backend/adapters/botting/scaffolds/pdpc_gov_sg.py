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
        # PROVISIONAL: selectors to be refined against live DOM
        return {
            "content_area": "main, #content, article, .page-content",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a, article a',
            "title": "h1, .page-title",
            "sections": "h2, h3, p, .guidance-section"
        }

    def get_keywords(self) -> list[str]:
        return [
            "data protection", "privacy", "pdpa", "personal data",
            "guidance", "framework", "regulation", "compliance",
            "singapore", "commissioner"
        ]

from .base_scaffold import BaseScaffold


class PDPMyScaffold(BaseScaffold):
    """Scaffold for Malaysia Personal Data Protection Department (pdp.gov.my)."""

    @property
    def target_domain(self) -> str:
        return "pdp.gov.my"

    def get_transport_type(self) -> str:
        return "auto"

    def get_custom_selectors(self) -> dict[str, str]:
        return {
            "content_area": ".content, main, #content, article",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": "main a, #content a, .content a",
            "title": "h1, .page-title",
            "sections": "h2, h3, p, li",
        }

    def get_boilerplate_selectors(self) -> list[str]:
        return [".breadcrumb", ".related", ".sidebar", ".footer", ".main-nav"]

    def get_keywords(self) -> list[str]:
        return [
            "personal data",
            "data protection",
            "pdpa",
            "privacy",
            "akta",
            "perlindungan data peribadi",
            "malaysia",
        ]

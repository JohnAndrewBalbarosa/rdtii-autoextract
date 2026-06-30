from .base_scaffold import BaseScaffold

class SSOAgcScaffold(BaseScaffold):
    """Scaffold for Singapore Statutes Online (sso.agc.gov.sg)."""

    @property
    def target_domain(self) -> str:
        return "sso.agc.gov.sg"

    def get_transport_type(self) -> str:
        # SSO typically serves static legislation pages.
        return "auto"

    def get_custom_selectors(self) -> dict[str, str]:
        # PROVISIONAL: selectors to be refined against live DOM
        return {
            "content_area": "main, #content, article, .legislation-body",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a, article a',
            "title": "h1, .act-title",
            "sections": "h2, h3, p, .section"
        }

    def get_keywords(self) -> list[str]:
        return [
            "act", "statute", "legislation", "law", "legal", "singapore",
            "ordinance", "regulation", "amendment", "principal act"
        ]

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .base_scaffold import BaseScaffold

class SSOAgcScaffold(BaseScaffold):
    """Scaffold for Singapore Statutes Online (sso.agc.gov.sg)."""

    @property
    def target_domain(self) -> str:
        return "sso.agc.gov.sg"

    def get_transport_type(self) -> str:
        # SSO typically serves static legislation pages.
        return "auto"

    def get_fetch_url(self, url: str) -> str:
        parsed = urlparse(url)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "ViewType" not in params and "ProvIds" not in params:
            params["ViewType"] = "Pdf"
        return urlunparse(parsed._replace(query=urlencode(params)))

    def get_custom_selectors(self) -> dict[str, str]:
        return {
            "content_area": "#legisContent, .prov1, .body-content, main, article",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a, article a',
            "title": "h1, .act-title",
            "sections": ".prov1, .prov2, h2, h3, p",
        }

    def get_boilerplate_selectors(self) -> list[str]:
        return [".global-nav", ".breadcrumb", ".legis-nav", "#toc", ".footer", ".sidebar"]

    def get_keywords(self) -> list[str]:
        return [
            "act", "statute", "legislation", "law", "legal", "singapore",
            "ordinance", "regulation", "amendment", "principal act"
        ]

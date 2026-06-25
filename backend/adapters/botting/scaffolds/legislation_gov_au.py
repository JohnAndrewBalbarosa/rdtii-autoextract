import re

from .base_scaffold import BaseScaffold

# Bare series URL: https://www.legislation.gov.au/C2004A02123  ->  add the text view.
_SERIES_URL_RE = re.compile(r"^(https?://(?:www\.)?legislation\.gov\.au/[A-Za-z0-9]+)/?$")


class LegislationGovAuScaffold(BaseScaffold):
    """Scaffold for the Australian Federal Register of Legislation (legislation.gov.au).

    The portal is an Angular SPA: the statute text renders client-side, so it is fetched
    dynamically. A bare series URL is rewritten to its ``/latest/text`` view, which carries
    the consolidated provision text rather than the metadata landing tab.
    """

    @property
    def target_domain(self) -> str:
        return "legislation.gov.au"

    def get_transport_type(self) -> str:
        return "dynamic"

    def get_fetch_url(self, url: str) -> str:
        match = _SERIES_URL_RE.match(url)
        if match:
            return f"{match.group(1)}/latest/text"
        return url

    def get_custom_selectors(self) -> dict[str, str]:
        return {
            "content_area": (
                "#legislationText, .legislation-text, [id*='-panel'], main, article"
            ),
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": "main a, article a",
            "title": "h1, .akn-docTitle",
            "sections": "h1, h2, h3, h4, p, li, .akn-section, .akn-subsection",
        }

    def get_boilerplate_selectors(self) -> list[str]:
        return [
            ".au-header", ".au-footer", ".cookie-banner", ".breadcrumb", ".nav-tabs",
            "[id*='Dropdown']", "[id*='Tab']", ".sidebar", ".skip-link",
        ]

    def get_keywords(self) -> list[str]:
        return [
            "act", "regulation", "legislation", "commonwealth", "section", "subsection",
            "part", "schedule", "amendment", "privacy", "data", "personal information",
        ]

import json
import os
from .base_scaffold import BaseScaffold

class PDPCScaffold(BaseScaffold):
    """Scaffold for Singapore Personal Data Protection Commission (pdpc.gov.sg)."""

    @property
    def target_domain(self) -> str:
        return "pdpc.gov.sg"

    def get_transport_type(self) -> str:
        # PDPC pages are typically static, but some may have interactive elements.
        return "auto"

    def _read_db_config(self) -> dict:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scaffolds_db.json")
        if os.path.exists(db_path):
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                    return configs.get(self.target_domain, {})
            except Exception:
                pass
        return {}

    def get_custom_selectors(self) -> dict[str, str]:
        cfg = self._read_db_config()
        if cfg:
            return {
                "content_area": cfg.get("content_area"),
                "pdf_links": cfg.get("pdf_links"),
                "article_links": cfg.get("article_links", "main a, #content a, article a"),
                "title": cfg.get("title"),
                "sections": cfg.get("sections")
            }
        return {
            "content_area": "main, #content, article, .page-content",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a, article a',
            "title": "h1, .page-title",
            "sections": "h2, h3, p, .guidance-section"
        }

    def get_keywords(self) -> list[str]:
        cfg = self._read_db_config()
        if cfg and "keywords" in cfg:
            return cfg["keywords"]
        return [
            "data protection", "privacy", "pdpa", "personal data",
            "guidance", "framework", "regulation", "compliance",
            "singapore", "commissioner"
        ]

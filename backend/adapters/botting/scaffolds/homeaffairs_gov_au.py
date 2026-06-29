import json
import os
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
                "article_links": cfg.get("article_links", "main a, #content a"),
                "title": cfg.get("title"),
                "sections": cfg.get("sections")
            }
        return {
            "content_area": "main, #content, article",
            "pdf_links": 'a[href$=".pdf"]',
            "article_links": 'main a, #content a',
            "title": "h1",
            "sections": "h2, h3, p"
        }

    def get_keywords(self) -> list[str]:
        cfg = self._read_db_config()
        if cfg and "keywords" in cfg:
            return cfg["keywords"]
        return [
            "law", "legislation", "framework", "legal", "act", 
            "regulation", "regulatory frameworks", "Cyber Security Act", 
            "legislative reforms"
        ]

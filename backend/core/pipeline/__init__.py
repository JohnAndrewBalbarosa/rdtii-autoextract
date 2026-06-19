"""Pipeline use-cases: discover -> retrieve -> ocr -> chunk -> extract -> map -> review.

Each stage is a pure function/use-case taking ports as dependencies (see
docs/ARCHITECTURE.md). Implemented per sprint.
"""
from .scraper_orchestrator import ScraperOrchestrator

__all__ = ["ScraperOrchestrator"]
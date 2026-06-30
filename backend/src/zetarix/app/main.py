"""FastAPI reference backend — thin HTTP layer over the framework-agnostic core.

This adapter contains NO domain logic. It maps HTTP <-> core use-cases so the
backend framework stays swappable (R12, R16). Replacing FastAPI with Litestar/Flask
touches only this package, never core/.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="RDTII Trade Regulatory Analysis Engine",
    version="0.1.0",
    description="Automates ~80% of the ESCAP RDTII workflow: search -> retrieve -> describe.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for self-hosted deployments (R16)."""
    return {"status": "ok"}


# Pipeline routes (discover -> retrieve -> ocr -> chunk -> extract -> map -> review)
# are wired here per sprint, delegating to core/pipeline use-cases with injected adapters.

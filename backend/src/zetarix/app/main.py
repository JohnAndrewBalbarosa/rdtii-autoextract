"""FastAPI reference backend — thin HTTP layer over the framework-agnostic core.

This adapter contains NO domain logic. It maps HTTP <-> core use-cases so the
backend framework stays swappable (R12, R16). Replacing FastAPI with Litestar/Flask
touches only this package, never core/.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zetarix.app.pipeline_routes import router as pipeline_router
from zetarix.pretrain.api.routes import router as training_router

app = FastAPI(
    title="RDTII Trade Regulatory Analysis Engine",
    version="0.1.0",
    description="Automates ~80% of the ESCAP RDTII workflow: search -> retrieve -> describe.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(training_router)
app.include_router(pipeline_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for self-hosted deployments (R16)."""
    return {"status": "ok"}


# Pipeline routes delegate to the same reviewer-contract pipeline used by the CLI.

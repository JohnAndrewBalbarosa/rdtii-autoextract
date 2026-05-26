"""Local model provider stub (implements core.ports.LLMProvider).

Wire a self-hosted, open-weight model here (e.g. Llama 3.1 via Ollama) for production.
This is intentionally a stub: the deterministic graph pipeline does not depend on it, and
this file plus remote_provider.py are the ONLY places to change when adding a real model.
"""

from __future__ import annotations


class LocalLLMProvider:
    """LLMProvider backed by a local/self-hosted model. Wire your model in `complete`."""

    def __init__(self, model: str = "llama3.1", endpoint: str = "http://localhost:11434") -> None:
        self._model = model
        self._endpoint = endpoint

    def complete(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError(
            "LocalLLMProvider is a stub. Wire your local model (e.g. Ollama "
            f"{self._model} at {self._endpoint}) here and return JSON matching `schema`."
        )

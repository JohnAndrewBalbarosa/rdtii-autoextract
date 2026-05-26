"""Remote model provider stub (implements core.ports.LLMProvider).

Wire a hosted API here (e.g. Claude or GPT) for development/evaluation. Intentionally a
stub: read the API key from the environment (never hardcode secrets) and return JSON
matching the requested schema. Paired with local_provider.py behind LLMRouter.
"""

from __future__ import annotations


class RemoteLLMProvider:
    """LLMProvider backed by a hosted API. Wire your provider call in `complete`."""

    def __init__(self, model: str = "claude-opus-4-7", api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError(
            "RemoteLLMProvider is a stub. Wire your hosted API call "
            f"(model={self._model}) here, read the key from the environment, and return "
            "JSON matching `schema`."
        )

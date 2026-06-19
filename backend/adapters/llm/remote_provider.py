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

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        # Based on agent_profile, we might swap out the model dynamically here
        # e.g., 'extraction_agent' -> gemini-1.5-flash, 'main_controller' -> gemini-1.5-pro
        model_to_use = "gemini-1.5-flash" if agent_profile in ("extraction_agent", "structuring_agent") else self._model

        raise NotImplementedError(
            "RemoteLLMProvider is a stub. Wire your hosted API call "
            f"(model={model_to_use}) here, read the key from the environment, and return "
            "JSON matching `schema`."
        )

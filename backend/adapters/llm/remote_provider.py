"""Remote model provider (implements core.ports.LLMProvider) — hosted API (Claude/GPT).

Reads the API key from the environment (never hardcode secrets) and returns JSON matching
the requested schema. Uses stdlib HTTP (no third-party SDK dependency). Paired with
local_provider.py behind LLMRouter; the deterministic pipeline never depends on this.

Env: ANTHROPIC_API_KEY (required), ZETARIX_LLM_MODEL (optional model override).
"""

from __future__ import annotations

import json
import os

from adapters.llm._jsonio import extract_json_object, post_json

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class RemoteLLMProvider:
    """LLMProvider backed by the Anthropic Messages API."""

    def __init__(self, model: str = "claude-3-5-sonnet-latest", api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Export it (or pass api_key=) to use RemoteLLMProvider."
            )
        model = os.environ.get("ZETARIX_LLM_MODEL", self._model)
        system = (
            "You extract structured data. Return ONLY a single JSON object that matches this "
            "JSON schema, with no prose, no markdown fences:\n" + json.dumps(schema)
        )
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        data = post_json(_ANTHROPIC_URL, payload, headers)
        text = "".join(block.get("text", "") for block in data.get("content", []))
        return extract_json_object(text)

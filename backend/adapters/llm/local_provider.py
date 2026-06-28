"""Local model provider (implements core.ports.LLMProvider) — self-hosted open weights.

Wires a local model served by Ollama (default Llama 3.1). Uses Ollama's JSON mode so the
response is a JSON object matching the requested schema. Stdlib HTTP only. The deterministic
graph pipeline does not depend on this; this and remote_provider.py are the only AI seams.

Env: ZETARIX_LLM_ENDPOINT (default http://localhost:11434), ZETARIX_LLM_MODEL (default llama3.1).
"""

from __future__ import annotations

import json
import os

from adapters.llm._jsonio import extract_json_object, post_json


class LocalLLMProvider:
    """LLMProvider backed by a local Ollama server."""

    def __init__(self, model: str = "llama3.1", endpoint: str = "http://localhost:11434") -> None:
        self._model = model
        self._endpoint = endpoint

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        endpoint = os.environ.get("ZETARIX_LLM_ENDPOINT", self._endpoint).rstrip("/")
        model = os.environ.get("ZETARIX_LLM_MODEL", self._model)
        system = (
            "You extract structured data. Return ONLY a JSON object matching this JSON schema:\n"
            + json.dumps(schema)
        )
        payload = {
            "model": model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        data = post_json(f"{endpoint}/api/chat", payload, {"content-type": "application/json"})
        text = (data.get("message") or {}).get("content", "")
        return extract_json_object(text)

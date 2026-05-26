"""Model-agnostic LLM middleman — the only swappable AI surface.

LLMRouter implements core.ports.LLMProvider and forwards `complete` to whichever backend
is selected (local or remote, set via the ZETARIX_LLM_BACKEND env var). Everything AI in
the system funnels through here; the deterministic graph stages never touch it. To change
models later, register a different provider here — nothing else changes.
"""

from __future__ import annotations

import os

from core.ports import LLMProvider

_ENV_BACKEND = "ZETARIX_LLM_BACKEND"
_DEFAULT_BACKEND = "remote"


class LLMRouter:
    """Routes LLMProvider.complete to the configured backend (local | remote)."""

    def __init__(self, providers: dict[str, LLMProvider], backend: str = _DEFAULT_BACKEND) -> None:
        if backend not in providers:
            raise ValueError(
                f"Unknown LLM backend {backend!r}; registered: {sorted(providers)}"
            )
        self._providers = providers
        self._backend = backend

    @classmethod
    def from_env(cls) -> "LLMRouter":
        """Build a router from env, lazily importing the stub providers."""
        from adapters.llm.local_provider import LocalLLMProvider
        from adapters.llm.remote_provider import RemoteLLMProvider

        providers: dict[str, LLMProvider] = {
            "local": LocalLLMProvider(),
            "remote": RemoteLLMProvider(),
        }
        backend = os.environ.get(_ENV_BACKEND, _DEFAULT_BACKEND)
        return cls(providers, backend)

    def complete(self, prompt: str, schema: dict) -> dict:
        return self._providers[self._backend].complete(prompt, schema)

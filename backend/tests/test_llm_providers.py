"""LLM provider layer (#9): remote (Anthropic) + local (Ollama) behind the router.

Network is mocked — these prove the request/response wiring + JSON parsing without a key.
"""

import pytest

from adapters.llm import local_provider, remote_provider
from adapters.llm._jsonio import extract_json_object
from adapters.llm.router import LLMRouter

SCHEMA = {"type": "object", "properties": {"indicator": {"type": "string"}}}


def test_extract_json_object_tolerates_prose_and_fences():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('Here you go:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json_object('prefix {"a": 3} suffix') == {"a": 3}
    with pytest.raises(ValueError):
        extract_json_object("no json here")


def test_remote_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        remote_provider.RemoteLLMProvider().complete("x", SCHEMA)


def test_remote_parses_anthropic_response(monkeypatch):
    captured = {}

    def fake_post(url, payload, headers, timeout=60):
        captured["url"] = url
        captured["headers"] = headers
        return {"content": [{"type": "text", "text": '{"indicator": "P6-I1"}'}]}

    monkeypatch.setattr(remote_provider, "post_json", fake_post)
    out = remote_provider.RemoteLLMProvider(api_key="k").complete("prompt", SCHEMA)
    assert out == {"indicator": "P6-I1"}
    assert "anthropic.com" in captured["url"]
    assert captured["headers"]["x-api-key"] == "k"


def test_local_parses_ollama_response(monkeypatch):
    def fake_post(url, payload, headers, timeout=60):
        assert url.endswith("/api/chat")
        return {"message": {"content": '{"indicator": "P7-I2"}'}}

    monkeypatch.setattr(local_provider, "post_json", fake_post)
    out = local_provider.LocalLLMProvider().complete("prompt", SCHEMA)
    assert out == {"indicator": "P7-I2"}


def test_router_selects_backend_and_delegates():
    class Fake:
        def __init__(self, tag):
            self.tag = tag

        def complete(self, prompt, schema, agent_profile="main_controller"):
            return {"backend": self.tag}

    router = LLMRouter({"local": Fake("local"), "remote": Fake("remote")}, backend="local")
    assert router.complete("p", SCHEMA) == {"backend": "local"}
    with pytest.raises(ValueError):
        LLMRouter({"local": Fake("local")}, backend="remote")


def test_router_from_env_respects_backend(monkeypatch):
    monkeypatch.setenv("ZETARIX_LLM_BACKEND", "local")
    router = LLMRouter.from_env()
    assert router._backend == "local"

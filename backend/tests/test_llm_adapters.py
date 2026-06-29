from __future__ import annotations

import os
import json
import pytest
from unittest.mock import patch, MagicMock
import urllib.error

from adapters.llm.remote_provider import (
    RemoteLLMProvider,
    validate_json_schema,
    prepare_prompt,
    parse_and_clean_json,
)
from adapters.llm.local_provider import LocalLLMProvider
from adapters.llm.router import LLMRouter


def test_validate_json_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "is_valid": {"type": "boolean"},
            "count": {"type": "integer"},
            "score": {"type": "number"},
            "name": {"type": "string"},
            "tags": {
                "type": "array",
                "items": {"type": "string"}
            },
            "info": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"}
                },
                "required": ["source"]
            }
        },
        "required": ["is_valid"]
    }

    # Valid data
    assert validate_json_schema({"is_valid": True}, schema)
    assert validate_json_schema({
        "is_valid": False,
        "count": 42,
        "score": 10.5,
        "name": "test",
        "tags": ["a", "b"],
        "info": {"source": "web"}
    }, schema)

    # Invalid cases
    assert not validate_json_schema({}, schema)  # missing required is_valid
    assert not validate_json_schema({"is_valid": "yes"}, schema)  # wrong type
    assert not validate_json_schema({"is_valid": True, "count": "42"}, schema)  # wrong type
    assert not validate_json_schema({"is_valid": True, "info": {}}, schema)  # missing sub-required source
    assert not validate_json_schema({"is_valid": True, "tags": [1, 2]}, schema)  # wrong array items type


def test_parse_and_clean_json() -> None:
    assert parse_and_clean_json('{"key": "value"}') == {"key": "value"}
    assert parse_and_clean_json('   {"key": "value"}   ') == {"key": "value"}
    
    # Markdown wrap
    assert parse_and_clean_json('```json\n{"key": "value"}\n```') == {"key": "value"}
    assert parse_and_clean_json('Here is your response:\n```\n{"key": "value"}\n```\nHope it helps!') == {"key": "value"}
    
    with pytest.raises(ValueError):
        parse_and_clean_json("invalid json string")


def test_prepare_prompt() -> None:
    prompt = "Hello"
    schema = {"type": "object"}
    prepared = prepare_prompt(prompt, schema)
    assert "Hello" in prepared
    assert "IMPORTANT" in prepared
    assert "JSON object" in prepared


def test_remote_provider_missing_keys(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    provider = RemoteLLMProvider()
    with pytest.raises(NotImplementedError) as exc_info:
        provider.complete("Test prompt", {"type": "object"})
    assert "No API key found" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_remote_provider_gemini_call(mock_urlopen, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-testkey-123")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Mock response
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "candidates": [
            {
                "content": {
                    "parts": [{"text": '{"is_valid": true}'}]
                }
            }
        ]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    provider = RemoteLLMProvider(model="gemini-3.1-flash")
    res = provider.complete("Is this legal?", {"type": "object", "properties": {"is_valid": {"type": "boolean"}}})
    
    assert res == {"is_valid": True}
    
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash:generateContent?key=gemini-testkey-123"


@patch("urllib.request.urlopen")
def test_remote_provider_anthropic_call(mock_urlopen, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-testkey")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Mock response
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "content": [{"text": '{"is_valid": true}'}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    provider = RemoteLLMProvider(model="claude-3-opus")
    res = provider.complete("Is this legal?", {"type": "object", "properties": {"is_valid": {"type": "boolean"}}})
    
    assert res == {"is_valid": True}
    
    # Check that mock urlopen was called with the correct Anthropic endpoint
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert req.headers["X-api-key"] == "sk-ant-testkey"
    assert req.headers["Anthropic-version"] == "2023-06-01"


@patch("urllib.request.urlopen")
def test_remote_provider_openai_call(mock_urlopen, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-open-testkey")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Mock response
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": '{"is_valid": false}'}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    provider = RemoteLLMProvider(model="gpt-4o")
    res = provider.complete("Is this legal?", {"type": "object", "properties": {"is_valid": {"type": "boolean"}}})
    
    assert res == {"is_valid": False}
    
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.full_url == "https://api.openai.com/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer sk-open-testkey"


def test_local_provider_missing_endpoint_offline() -> None:
    # Use a non-existent port to force connection refused / URLError
    provider = LocalLLMProvider(endpoint="http://localhost:59999")
    with pytest.raises(NotImplementedError) as exc_info:
        provider.complete("Test prompt", {"type": "object"})
    assert "Ollama server is offline" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_local_provider_ollama_call(mock_urlopen) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": '{"is_valid": true}'}
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    provider = LocalLLMProvider(model="gpt-oss:20b", endpoint="http://localhost:11434")
    res = provider.complete("Is this legal?", {"type": "object", "properties": {"is_valid": {"type": "boolean"}}})
    
    assert res == {"is_valid": True}
    
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.full_url == "http://localhost:11434/api/chat"
    
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "gpt-oss:20b"
    assert body["format"] == "json"


def test_llm_router_routing(monkeypatch) -> None:
    monkeypatch.setenv("ZETARIX_LLM_BACKEND", "local")
    router = LLMRouter.from_env()
    assert router._backend == "local"

    monkeypatch.setenv("ZETARIX_LLM_BACKEND", "remote")
    router = LLMRouter.from_env()
    assert router._backend == "remote"


def test_llm_router_hybrid_routing() -> None:
    local_mock = MagicMock()
    remote_mock = MagicMock()

    providers = {
        "local": local_mock,
        "remote": remote_mock
    }

    router = LLMRouter(providers, backend="hybrid")

    # main_controller -> remote
    router.complete("test prompt", {}, agent_profile="main_controller")
    remote_mock.complete.assert_called_once_with("test prompt", {}, "main_controller")
    local_mock.complete.assert_not_called()

    # reset mocks
    local_mock.reset_mock()
    remote_mock.reset_mock()

    # extraction_agent -> local
    router.complete("test prompt", {}, agent_profile="extraction_agent")
    local_mock.complete.assert_called_once_with("test prompt", {}, "extraction_agent")
    remote_mock.complete.assert_not_called()

"""Local model provider stub (implements zetarix.ports.LLMProvider).

Wire a self-hosted, open-weight model here (e.g. gpt-oss:20b via Ollama) for production.
This is intentionally a stub: the deterministic graph pipeline does not depend on it, and
this file plus remote_provider.py are the ONLY places to change when adding a real model.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error


def validate_json_schema(data: any, schema: dict) -> bool:
    if not isinstance(schema, dict):
        return True
    
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(data, dict):
            return False
        properties = schema.get("properties", {})
        for k, prop_schema in properties.items():
            if k in data:
                if not validate_json_schema(data[k], prop_schema):
                    return False
        required = schema.get("required", [])
        for req_key in required:
            if req_key not in data:
                return False
    elif expected_type == "array":
        if not isinstance(data, list):
            return False
        items_schema = schema.get("items")
        if items_schema:
            for item in data:
                if not validate_json_schema(item, items_schema):
                    return False
    elif expected_type == "string":
        if not isinstance(data, str):
            return False
    elif expected_type == "integer":
        if isinstance(data, bool) or not isinstance(data, int):
            return False
    elif expected_type == "number":
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            return False
    elif expected_type == "boolean":
        if not isinstance(data, bool):
            return False
    return True


def prepare_prompt(prompt: str, schema: dict) -> str:
    instructions = (
        "\n\nIMPORTANT: You must respond ONLY with a JSON object that conforms to the following schema.\n"
        "Do NOT include any conversational filler, markdown formatting (like ```json), or extra text.\n"
        f"Schema:\n{json.dumps(schema, indent=2)}"
    )
    return prompt + instructions


def parse_and_clean_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON object between first '{' and last '}'
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1:
        candidate = text[first_brace:last_brace+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse valid JSON from LLM response: {text!r}")


class LocalLLMProvider:
    """LLMProvider backed by a local/self-hosted model (Ollama)."""

    def __init__(self, model: str | None = None, endpoint: str | None = None) -> None:
        self._model = model or os.environ.get("OLLAMA_MODEL") or "gpt-oss:20b"
        self._endpoint = endpoint or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        headers = {
            "Content-Type": "application/json",
        }
        augmented_prompt = prepare_prompt(prompt, schema)
        
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": augmented_prompt}
            ],
            "stream": False,
            "format": "json"
        }
        
        url = f"{self._endpoint.rstrip('/')}/api/chat"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        res_text = ""
        try:
            # Increase timeout to 180 seconds to give large models (like gpt-oss:20b)
            # sufficient time to load weights and perform inference.
            with urllib.request.urlopen(req, timeout=180) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                res_text = res_body["message"]["content"]
        except urllib.error.URLError as e:
            raise NotImplementedError(
                f"LocalLLMProvider: Ollama server is offline or unreachable at {self._endpoint}. "
                f"Details: {e}"
            )
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8")
            if e.code == 404:
                raise NotImplementedError(
                    f"LocalLLMProvider: Model '{self._model}' is not pulled in Ollama. "
                    f"Details: {err_content}"
                )
            raise RuntimeError(f"Ollama call failed with HTTP error: {e.code} {e.reason} - {err_content}")
        except Exception as e:
            raise NotImplementedError(
                f"LocalLLMProvider: Failed to communicate with Ollama: {e}"
            )

        # Self-healing fallback: If Ollama's constrained JSON mode causes the model to return
        # an empty response, we retry in plain-text mode and let our custom parser extract the JSON.
        if not res_text.strip():
            payload.pop("format", None)
            plain_prompt = prompt + (
                "\n\nRespond ONLY with a JSON object conforming to the schema below. "
                "You may enclose the JSON in a ```json ... ``` codeblock. Do not include any other text.\n"
                f"Schema:\n{json.dumps(schema, indent=2)}"
            )
            payload["messages"][0]["content"] = plain_prompt
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    res_text = res_body["message"]["content"]
            except Exception as e:
                raise RuntimeError(
                    f"LocalLLMProvider: Plain-text retry failed for Ollama: {e}"
                )

        parsed_json = parse_and_clean_json(res_text)
        if not validate_json_schema(parsed_json, schema):
            raise ValueError(
                f"Local Ollama response does not conform to the expected schema.\n"
                f"Response: {json.dumps(parsed_json)}\n"
                f"Schema: {json.dumps(schema)}"
            )
        return parsed_json

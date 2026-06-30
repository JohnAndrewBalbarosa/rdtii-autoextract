"""Remote model provider stub (implements zetarix.ports.LLMProvider).

Wire a hosted API here (e.g. Claude, GPT, or Gemini) for development/evaluation.
Read the API key from the environment (never hardcode secrets) and return JSON
matching the requested schema. Paired with local_provider.py behind LLMRouter.
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


def to_gemini_schema(schema: dict) -> dict:
    """Recursively converts standard JSON schema type names to Gemini's uppercase format."""
    if not isinstance(schema, dict):
        return schema
    
    new_schema = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            type_map = {
                "object": "OBJECT",
                "array": "ARRAY",
                "string": "STRING",
                "integer": "INTEGER",
                "number": "NUMBER",
                "boolean": "BOOLEAN"
            }
            new_schema[k] = type_map.get(v.lower(), v.upper())
        elif isinstance(v, dict):
            new_schema[k] = to_gemini_schema(v)
        elif isinstance(v, list):
            new_schema[k] = [to_gemini_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            new_schema[k] = v
    return new_schema


class RemoteLLMProvider:
    """LLMProvider backed by a hosted API (Gemini, Anthropic Claude, or OpenAI GPT)."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or os.environ.get("REMOTE_LLM_MODEL") or "gemini-1.5-flash"
        self._api_key = api_key

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        # Respect the configured model for all tasks
        model_to_use = self._model

        # Determine the key to use
        api_key = self._api_key
        if not api_key:
            if "gemini" in model_to_use.lower():
                api_key = os.environ.get("GEMINI_API_KEY")
            elif "claude" in model_to_use.lower() or "anthropic" in model_to_use.lower():
                api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
            elif "gpt" in model_to_use.lower() or "openai" in model_to_use.lower():
                api_key = os.environ.get("OPENAI_API_KEY")
            else:
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("ANTHROPIC_API_KEY")
                    or os.environ.get("CLAUDE_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                )

        if not api_key:
            raise NotImplementedError(
                "RemoteLLMProvider: No API key found. Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY."
            )

        # Route to Gemini, Anthropic or OpenAI based on keys and model
        is_gemini = False
        is_anthropic = False
        is_openai = False

        gemini_key = os.environ.get("GEMINI_API_KEY")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if self._api_key:
            if "gemini" in model_to_use.lower():
                is_gemini = True
            elif "claude" in model_to_use.lower() or "anthropic" in model_to_use.lower():
                is_anthropic = True
            elif "gpt" in model_to_use.lower() or "openai" in model_to_use.lower():
                is_openai = True
            else:
                if self._api_key.startswith("AIzaSy"):
                    is_gemini = True
                elif len(self._api_key) > 40:
                    is_anthropic = True
                else:
                    is_openai = True
        else:
            if "gemini" in model_to_use.lower():
                if gemini_key:
                    is_gemini = True
                elif anthropic_key:
                    is_anthropic = True
                    model_to_use = "claude-3-5-sonnet-20240620"
                elif openai_key:
                    is_openai = True
                    model_to_use = "gpt-4o-mini"
            elif "claude" in model_to_use.lower() or "anthropic" in model_to_use.lower():
                if anthropic_key:
                    is_anthropic = True
                elif gemini_key:
                    is_gemini = True
                    model_to_use = "gemini-1.5-flash"
                elif openai_key:
                    is_openai = True
                    model_to_use = "gpt-4o-mini"
            elif "gpt" in model_to_use.lower() or "openai" in model_to_use.lower():
                if openai_key:
                    is_openai = True
                elif gemini_key:
                    is_gemini = True
                    model_to_use = "gemini-1.5-flash"
                elif anthropic_key:
                    is_anthropic = True
                    model_to_use = "claude-3-5-sonnet-20240620"
            else:
                if gemini_key:
                    is_gemini = True
                    model_to_use = "gemini-1.5-flash"
                elif anthropic_key:
                    is_anthropic = True
                    model_to_use = "claude-3-5-sonnet-20240620"
                elif openai_key:
                    is_openai = True
                    model_to_use = "gpt-4o-mini"

        active_key = self._api_key or (gemini_key if is_gemini else (anthropic_key if is_anthropic else openai_key))
        res_text = ""

        if is_gemini:
            # Call native Gemini API directly to avoid permission 403s on the OpenAI compatible layer
            headers = {
                "Content-Type": "application/json",
            }
            augmented_prompt = prepare_prompt(prompt, schema)
            gemini_schema = to_gemini_schema(schema)
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": augmented_prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": gemini_schema
                }
            }
            
            model_name = model_to_use
            if not model_name.startswith("models/"):
                model_name = f"models/{model_name}"

            url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={active_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    res_text = res_body["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8")
                raise RuntimeError(f"Gemini API call failed: {e.code} {e.reason} - {err_content}")
            except Exception as e:
                raise RuntimeError(f"Gemini API connection failed: {e}")

        elif is_anthropic:
            headers = {
                "x-api-key": active_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            augmented_prompt = prepare_prompt(prompt, schema)
            payload = {
                "model": model_to_use,
                "max_tokens": 4000,
                "messages": [
                    {"role": "user", "content": augmented_prompt}
                ]
            }
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    res_text = res_body["content"][0]["text"]
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8")
                raise RuntimeError(f"Anthropic API call failed: {e.code} {e.reason} - {err_content}")
            except Exception as e:
                raise RuntimeError(f"Anthropic API connection failed: {e}")

        elif is_openai:
            headers = {
                "Authorization": f"Bearer {active_key}",
                "Content-Type": "application/json",
            }
            augmented_prompt = prepare_prompt(prompt, schema)
            payload = {
                "model": model_to_use,
                "messages": [
                    {"role": "user", "content": augmented_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    res_text = res_body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8")
                raise RuntimeError(f"OpenAI API call failed: {e.code} {e.reason} - {err_content}")
            except Exception as e:
                raise RuntimeError(f"OpenAI API connection failed: {e}")

        parsed_json = parse_and_clean_json(res_text)
        if not validate_json_schema(parsed_json, schema):
            raise ValueError(
                f"Response JSON does not conform to the expected schema.\n"
                f"Response: {json.dumps(parsed_json)}\n"
                f"Schema: {json.dumps(schema)}"
            )
        return parsed_json

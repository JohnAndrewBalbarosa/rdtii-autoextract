"""Tiny stdlib HTTP+JSON helpers shared by the LLM providers (no third-party deps).

Kept separate so providers stay thin and the network call is a single mockable seam.
"""

from __future__ import annotations

import json
import re
import urllib.request

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    """POST ``payload`` as JSON and return the decoded JSON response."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted host)
        return json.loads(response.read().decode("utf-8"))


def extract_json_object(text: str) -> dict:
    """Parse the first JSON object out of model text (tolerates prose around it)."""
    text = (text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJ_RE.search(text)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))

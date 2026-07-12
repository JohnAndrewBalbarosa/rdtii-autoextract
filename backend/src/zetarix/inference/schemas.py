"""Runtime JSON schemas for Law Interpreter and Tag Generator LLM outputs."""

from __future__ import annotations

from typing import Any

LAW_INTERPRETER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "obligation_type": {
            "type": "string",
            "enum": ["prohibition", "requirement", "permission", "accountability", "assessment", "other"],
        },
        "scope": {"type": "string"},
        "applicability_triggers": {"type": "array", "items": {"type": "string"}},
        "plain_summary": {"type": "string"},
    },
    "required": ["obligation_type", "scope", "applicability_triggers", "plain_summary"],
}


TAG_GENERATOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "indicator_tags": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["indicator_tags", "rationale"],
}

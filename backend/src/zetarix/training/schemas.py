"""Backward-compatible shim — use ``zetarix.pretrain.dataset.schemas`` / ``zetarix.inference.schemas``."""

from zetarix.inference.schemas import LAW_INTERPRETER_OUTPUT_SCHEMA, TAG_GENERATOR_OUTPUT_SCHEMA
from zetarix.pretrain.dataset.schemas import (
    LabelKind,
    LawInterpreterExample,
    ReviewDecision,
    TagGeneratorExample,
)

__all__ = [
    "LAW_INTERPRETER_OUTPUT_SCHEMA",
    "TAG_GENERATOR_OUTPUT_SCHEMA",
    "LabelKind",
    "LawInterpreterExample",
    "ReviewDecision",
    "TagGeneratorExample",
]

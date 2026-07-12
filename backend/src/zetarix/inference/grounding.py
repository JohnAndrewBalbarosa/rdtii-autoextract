"""Factory for grounded Law Interpreter / Tag Generator pipeline components."""

from __future__ import annotations

import os
from pathlib import Path

from zetarix.extraction.law_interpreter import LawInterpreter
from zetarix.extraction.tag_generator import TagGenerator
from zetarix.ports import LLMProvider
from zetarix.inference.few_shot import FewShotRetriever
from zetarix.pretrain.paths import SPLITS_DIR

_DEFAULT_SPLITS = SPLITS_DIR


def default_splits_dir() -> Path:
    return Path(os.environ.get("ZETARIX_TRAINING_SPLITS", _DEFAULT_SPLITS))


def load_retriever(splits_dir: Path | str | None = None) -> FewShotRetriever | None:
    """Load the few-shot retriever if training splits exist; else None."""
    root = Path(splits_dir) if splits_dir else default_splits_dir()
    law_train = root / "law_interpreter_train.jsonl"
    tag_train = root / "tag_generator_train.jsonl"
    if not law_train.exists() or not tag_train.exists():
        return None
    return FewShotRetriever.from_splits_dir(root)


def create_law_interpreter(llm: LLMProvider, *, retriever: FewShotRetriever | None = None) -> LawInterpreter:
    resolved = retriever if retriever is not None else load_retriever()
    return LawInterpreter.from_env(llm, retriever=resolved)


def create_tag_generator(llm: LLMProvider, *, retriever: FewShotRetriever | None = None) -> TagGenerator:
    resolved = retriever if retriever is not None else load_retriever()
    return TagGenerator.from_env(llm, retriever=resolved)

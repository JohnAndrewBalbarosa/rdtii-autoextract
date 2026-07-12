"""Runtime model integration: few-shot grounding, vocabulary, and SetTrie."""

from zetarix.inference.few_shot import FewShotRetriever
from zetarix.inference.grounding import (
    create_law_interpreter,
    create_tag_generator,
    default_splits_dir,
    load_retriever,
)

__all__ = [
    "FewShotRetriever",
    "create_law_interpreter",
    "create_tag_generator",
    "default_splits_dir",
    "load_retriever",
]

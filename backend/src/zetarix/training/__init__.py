"""Training data pipeline (backward-compatible package).

New code should import from:
- ``zetarix.pretrain`` — dataset build, labeling, fine-tune, eval, API
- ``zetarix.inference`` — few-shot grounding, vocabulary, SetTrie at runtime
"""

from zetarix.inference import FewShotRetriever, create_law_interpreter, create_tag_generator, load_retriever
from zetarix.pretrain.dataset.build import DatasetCounts, build_datasets, count_examples
from zetarix.pretrain.dataset.review_log import load_review_decisions
from zetarix.pretrain.dataset.schemas import LawInterpreterExample, TagGeneratorExample

__all__ = [
    "DatasetCounts",
    "FewShotRetriever",
    "LawInterpreterExample",
    "TagGeneratorExample",
    "build_datasets",
    "count_examples",
    "create_law_interpreter",
    "create_tag_generator",
    "load_retriever",
    "load_review_decisions",
]

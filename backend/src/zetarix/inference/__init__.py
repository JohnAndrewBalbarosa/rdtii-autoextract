"""Runtime model integration: few-shot grounding, vocabulary, and SetTrie."""

from zetarix.inference.few_shot import FewShotRetriever

__all__ = [
    "FewShotRetriever",
    "create_law_interpreter",
    "create_tag_generator",
    "default_splits_dir",
    "load_retriever",
]


def __getattr__(name: str):
    if name in __all__ and name != "FewShotRetriever":
        from zetarix.inference import grounding

        return getattr(grounding, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

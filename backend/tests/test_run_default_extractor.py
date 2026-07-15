from __future__ import annotations

import run


def test_default_extractor_does_not_enable_reviewer_llm_by_default(monkeypatch):
    monkeypatch.delenv("ZETARIX_ENABLE_REVIEWER_LLM", raising=False)

    extractor = run._default_extractor()

    assert extractor._briefs._llm is None


def test_default_extractor_enables_reviewer_llm_only_when_opted_in(monkeypatch):
    class _FakeRouter:
        @classmethod
        def from_env(cls):
            return object()

    monkeypatch.setenv("ZETARIX_ENABLE_REVIEWER_LLM", "1")
    monkeypatch.setitem(run._default_extractor.__globals__, "os", run.os)

    import sys
    import types

    fake_module = types.ModuleType("zetarix.llm.router")
    fake_module.LLMRouter = _FakeRouter
    monkeypatch.setitem(sys.modules, "zetarix.llm.router", fake_module)

    extractor = run._default_extractor()

    assert extractor._briefs._llm is not None

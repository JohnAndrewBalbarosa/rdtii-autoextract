from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.domain.access import (
    AccessDecision,
    AccessDecisionKind,
    AccessLayer,
    AccessSignal,
    AccessSignalSeverity,
    RetrievalPolicy,
)
from core.pipeline.compliant_retrieval import (
    CompliantRetrievalPipeline,
    InMemoryRetrievalAuditor,
    StaticAccessPolicyEvaluator,
)

FIXED_TIMESTAMP = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


class FakeDocumentSource:
    def __init__(self, fetch_map: dict[str, object]) -> None:
        self._fetch_map = dict(fetch_map)
        self.fetch_calls: list[str] = []

    def discover(self, jurisdiction: str, pillars: list[int]) -> list[str]:
        return []

    def fetch(self, url: str) -> bytes:
        self.fetch_calls.append(url)
        response = self._fetch_map[url]
        if callable(response):
            response = response()
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, str):
            return response.encode("utf-8")
        return response


class FakeAccessObserver:
    def __init__(self, signal_factory) -> None:
        self._signal_factory = signal_factory
        self.calls: list[tuple[str, object]] = []

    def observe(self, source_url: str, outcome: object) -> list[AccessSignal]:
        self.calls.append((source_url, outcome))
        return list(self._signal_factory(source_url, outcome))


class FlakyResponse:
    def __init__(self, failures_before_success: int, success_value: bytes) -> None:
        self.failures_before_success = failures_before_success
        self.success_value = success_value
        self.calls = 0

    def __call__(self) -> bytes:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("temporary network failure")
        return self.success_value


def _signal(
    source_url: str,
    status: str,
    detail: str,
    severity: AccessSignalSeverity,
    layer: AccessLayer,
) -> AccessSignal:
    return AccessSignal(
        layer=layer,
        source_url=source_url,
        status=status,
        detail=detail,
        severity=severity,
        timestamp=FIXED_TIMESTAMP,
    )


def _build_pipeline(
    document_source: FakeDocumentSource,
    observer: FakeAccessObserver,
    auditor: InMemoryRetrievalAuditor,
) -> CompliantRetrievalPipeline:
    return CompliantRetrievalPipeline(
        document_source=document_source,
        observer=observer,
        policy_evaluator=StaticAccessPolicyEvaluator(),
        auditor=auditor,
    )


def test_approved_source_returns_content_and_records_audit_event() -> None:
    source_url = "https://example.gov/approved"
    document_source = FakeDocumentSource({source_url: b"approved-content"})
    observer = FakeAccessObserver(
        lambda url, outcome: [
            _signal(
                url,
                "approved",
                "approved retrieval",
                AccessSignalSeverity.INFO,
                AccessLayer.APPLICATION,
            )
        ]
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.content == b"approved-content"
    assert result.decision.kind == AccessDecisionKind.ALLOW
    assert result.audit_events
    assert result.audit_events[0].source_url == source_url
    assert result.audit_events[0].decision == result.decision
    assert document_source.fetch_calls == [source_url]
    assert observer.calls == [(source_url, b"approved-content")]


def test_unauthorized_source_denies_without_fetching_source() -> None:
    source_url = "https://example.gov/restricted"
    document_source = FakeDocumentSource({source_url: b"should-not-be-fetched"})
    observer = FakeAccessObserver(lambda url, outcome: [])
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=False,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.DENY
    assert result.content is None
    assert result.audit_events[0].source_url == source_url
    assert result.audit_events[0].decision.kind == AccessDecisionKind.DENY
    assert auditor.events == list(result.audit_events)
    assert document_source.fetch_calls == []
    assert observer.calls == []


def test_policy_source_url_mismatch_denies_without_fetching_source() -> None:
    source_url = "https://example.gov/requested"
    policy_url = "https://example.gov/policy"
    document_source = FakeDocumentSource({source_url: b"should-not-be-fetched"})
    observer = FakeAccessObserver(lambda url, outcome: [])
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=policy_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.DENY
    assert result.content is None
    assert result.audit_events[0].source_url == source_url
    assert result.audit_events[0].decision.kind == AccessDecisionKind.DENY
    assert auditor.events == list(result.audit_events)
    assert document_source.fetch_calls == []
    assert observer.calls == []


def test_exhausted_rate_budget_retries_later_without_fetching_source() -> None:
    source_url = "https://example.gov/rate-budget"
    document_source = FakeDocumentSource({source_url: b"should-not-be-fetched"})
    observer = FakeAccessObserver(lambda url, outcome: [])
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=0,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.RETRY_LATER
    assert result.content is None
    assert result.audit_events[0].source_url == source_url
    assert result.audit_events[0].decision.kind == AccessDecisionKind.RETRY_LATER
    assert auditor.events == list(result.audit_events)
    assert document_source.fetch_calls == []
    assert observer.calls == []


def test_rate_limit_budget_bounds_retry_attempts() -> None:
    source_url = "https://example.gov/budgeted-retry"
    document_source = FakeDocumentSource(
        {source_url: FlakyResponse(failures_before_success=1, success_value=b"unused")}
    )
    observer = FakeAccessObserver(
        lambda url, outcome: [
            _signal(
                url,
                "network_error",
                "temporary network failure",
                AccessSignalSeverity.ERROR,
                AccessLayer.NETWORK,
            )
        ]
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=1,
        max_retries=3,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.RETRY_LATER
    assert result.content is None
    assert document_source.fetch_calls == [source_url]


def test_transient_network_error_returns_retry_later_when_budget_is_exhausted() -> None:
    source_url = "https://example.gov/transient"
    document_source = FakeDocumentSource(
        {source_url: FlakyResponse(failures_before_success=1, success_value=b"unused")}
    )
    observer = FakeAccessObserver(
        lambda url, outcome: []
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=0,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.RETRY_LATER
    assert result.content is None
    assert document_source.fetch_calls == [source_url]
    assert observer.calls and isinstance(observer.calls[0][1], TimeoutError)


def test_transient_network_error_retries_when_budget_remains() -> None:
    source_url = "https://example.gov/transient-retry"
    document_source = FakeDocumentSource(
        {source_url: FlakyResponse(failures_before_success=1, success_value=b"retrieved")}
    )
    observer = FakeAccessObserver(
        lambda url, outcome: []
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.ALLOW
    assert result.content == b"retrieved"
    assert document_source.fetch_calls == [source_url, source_url]
    assert len(observer.calls) == 2


@pytest.mark.parametrize(
    ("signal_status", "signal_detail"),
    (
        ("captcha", "captcha challenge"),
        ("challenge", "access challenge"),
        ("auth", "authentication required"),
        ("identity", "identity verification required"),
    ),
)
def test_challenge_signal_returns_handoff_without_content(
    signal_status: str, signal_detail: str
) -> None:
    source_url = "https://example.gov/challenge"
    document_source = FakeDocumentSource({source_url: b"challenge-payload"})
    observer = FakeAccessObserver(
        lambda url, outcome: [
            _signal(
                url,
                signal_status,
                signal_detail,
                AccessSignalSeverity.ERROR,
                AccessLayer.SESSION,
            )
        ]
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.HANDOFF
    assert result.content is None
    assert document_source.fetch_calls == [source_url]
    assert observer.calls == [(source_url, b"challenge-payload")]


@pytest.mark.parametrize(
    (
        "approved_fallback_urls",
        "expected_kind",
        "expected_content",
        "expected_fallback",
        "expect_fallback_event",
    ),
    (
        ((), AccessDecisionKind.RETRY_LATER, None, None, False),
        (
            ("https://archive.example/fallback",),
            AccessDecisionKind.ALLOW,
            b"fallback-content",
            "https://archive.example/fallback",
            True,
        ),
    ),
)
def test_approved_fallback_is_used_only_when_policy_lists_fallback_url(
    approved_fallback_urls: tuple[str, ...],
    expected_kind: AccessDecisionKind,
    expected_content: bytes | None,
    expected_fallback: str | None,
    expect_fallback_event: bool,
) -> None:
    source_url = "https://example.gov/primary"
    fallback_url = "https://archive.example/fallback"
    document_source = FakeDocumentSource(
        {
            source_url: FileNotFoundError("content not available"),
            fallback_url: b"fallback-content",
        }
    )
    observer = FakeAccessObserver(
        lambda url, outcome: (
            [
                _signal(
                    url,
                    "missing",
                    "content not available at primary source",
                    AccessSignalSeverity.WARNING,
                    AccessLayer.APPLICATION,
                )
            ]
            if isinstance(outcome, BaseException)
            else [
                _signal(
                    url,
                    "approved",
                    "approved retrieval",
                    AccessSignalSeverity.INFO,
                    AccessLayer.APPLICATION,
                )
            ]
        )
    )
    auditor = InMemoryRetrievalAuditor()
    pipeline = _build_pipeline(document_source, observer, auditor)
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=0,
        approved_fallback_urls=approved_fallback_urls,
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == expected_kind
    assert result.content == expected_content
    assert result.fallback_used == expected_fallback
    if expect_fallback_event:
        assert result.audit_events[0].decision.kind == AccessDecisionKind.USE_APPROVED_FALLBACK
        assert result.audit_events[-1].decision.kind == AccessDecisionKind.ALLOW
    if expected_fallback is None:
        assert document_source.fetch_calls == [source_url]
    else:
        assert document_source.fetch_calls == [source_url, fallback_url]


def test_unapproved_evaluator_fallback_url_routes_to_handoff() -> None:
    source_url = "https://example.gov/primary"
    unapproved_fallback_url = "https://unapproved.example/fallback"
    document_source = FakeDocumentSource(
        {
            source_url: FileNotFoundError("content not available"),
            unapproved_fallback_url: b"must-not-fetch",
        }
    )
    observer = FakeAccessObserver(
        lambda url, outcome: [
            _signal(
                url,
                "missing",
                "content not available at primary source",
                AccessSignalSeverity.WARNING,
                AccessLayer.APPLICATION,
            )
        ]
    )
    auditor = InMemoryRetrievalAuditor()

    class UnapprovedFallbackEvaluator:
        def evaluate(self, signals, policy, attempt):  # noqa: ANN001, ANN201
            return AccessDecision(
                kind=AccessDecisionKind.USE_APPROVED_FALLBACK,
                reason="buggy evaluator returned unapproved fallback",
                fallback_url=unapproved_fallback_url,
            )

    pipeline = CompliantRetrievalPipeline(
        document_source=document_source,
        observer=observer,
        policy_evaluator=UnapprovedFallbackEvaluator(),
        auditor=auditor,
    )
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=0,
        approved_fallback_urls=("https://archive.example/approved",),
        policy_version="policy-v1",
    )

    result = pipeline.fetch(source_url, policy)

    assert result.decision.kind == AccessDecisionKind.HANDOFF
    assert result.content is None
    assert document_source.fetch_calls == [source_url]


def test_same_inputs_produce_same_decision_kinds_and_content() -> None:
    source_url = "https://example.gov/deterministic"
    policy = RetrievalPolicy(
        source_url=source_url,
        authorized=True,
        rate_limit_budget=3,
        max_retries=1,
        approved_fallback_urls=(),
        policy_version="policy-v1",
    )

    def build_and_run() -> object:
        document_source = FakeDocumentSource({source_url: b"stable-content"})
        observer = FakeAccessObserver(
            lambda url, outcome: [
                _signal(
                    url,
                    "approved",
                    "approved retrieval",
                    AccessSignalSeverity.INFO,
                    AccessLayer.APPLICATION,
                )
            ]
        )
        auditor = InMemoryRetrievalAuditor()
        pipeline = _build_pipeline(document_source, observer, auditor)
        return pipeline.fetch(source_url, policy)

    first = build_and_run()
    second = build_and_run()

    assert first.decision.kind == second.decision.kind
    assert first.content == second.content
    assert first.fallback_used == second.fallback_used

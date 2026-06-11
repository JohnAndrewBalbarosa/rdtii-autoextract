"""Deterministic compliant retrieval pipeline.

This module keeps the retrieval policy gate explicit and framework-agnostic:
- the document source is injected as a port
- access signals are produced by an injected observer
- policy decisions come from an injected evaluator
- audit events are written only through the injected auditor

No network libraries, model SDKs, or stealth/bypass logic are used here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from core.domain.access import (
    AccessDecision,
    AccessDecisionKind,
    AccessSignal,
    AccessSignalSeverity,
    RetrievalAuditEvent,
    RetrievalPolicy,
    RetrievalResult,
)
from core.ports import DocumentSource
from core.ports.access import AccessObserver, AccessPolicyEvaluator, RetrievalAuditor


class InMemoryRetrievalAuditor:
    """Simple audit sink that retains events in memory."""

    def __init__(self) -> None:
        self.events: list[RetrievalAuditEvent] = []

    def record(self, event: RetrievalAuditEvent) -> None:
        self.events.append(event)


class StaticAccessPolicyEvaluator:
    """Deterministic reference evaluator for compliant retrieval."""

    _BLOCKING_STATUSES = ("captcha", "challenge", "forbidden", "auth", "identity")
    _RETRY_STATUSES = ("throttle", "rate")
    _FALLBACK_STATUSES = ("missing", "not_found")

    def evaluate(
        self,
        signals: Sequence[AccessSignal],
        policy: RetrievalPolicy,
        attempt: int,
    ) -> AccessDecision:
        if not policy.authorized:
            return AccessDecision(kind=AccessDecisionKind.DENY, reason="policy not authorized")

        statuses = tuple(signal.status.lower() for signal in signals)

        if self._contains_any(statuses, self._BLOCKING_STATUSES):
            return AccessDecision(kind=AccessDecisionKind.HANDOFF, reason="blocking access signal detected")

        if self._contains_any(statuses, self._RETRY_STATUSES):
            if attempt <= policy.max_retries:
                return AccessDecision(kind=AccessDecisionKind.RETRY_LATER, reason="throttled or rate limited")
            return AccessDecision(kind=AccessDecisionKind.HANDOFF, reason="throttling persisted beyond retry budget")

        if any(signal.severity is AccessSignalSeverity.ERROR for signal in signals):
            if attempt <= policy.max_retries:
                return AccessDecision(kind=AccessDecisionKind.RETRY_LATER, reason="error severity signal")
            return AccessDecision(kind=AccessDecisionKind.DENY, reason="error severity persisted beyond retry budget")

        if policy.approved_fallback_urls and self._contains_any(statuses, self._FALLBACK_STATUSES):
            return AccessDecision(
                kind=AccessDecisionKind.USE_APPROVED_FALLBACK,
                reason="approved fallback available for missing content",
                fallback_url=policy.approved_fallback_urls[0],
            )

        return AccessDecision(kind=AccessDecisionKind.ALLOW, reason="allowed")

    @staticmethod
    def _contains_any(statuses: Sequence[str], needles: Sequence[str]) -> bool:
        return any(needle in status for status in statuses for needle in needles)


class CompliantRetrievalPipeline:
    """Fetch content through an explicit policy gate and audit every decision."""

    def __init__(
        self,
        document_source: DocumentSource,
        observer: AccessObserver,
        policy_evaluator: AccessPolicyEvaluator,
        auditor: RetrievalAuditor,
    ) -> None:
        self._document_source = document_source
        self._observer = observer
        self._policy_evaluator = policy_evaluator
        self._auditor = auditor

    def fetch(self, source_url: str, policy: RetrievalPolicy) -> RetrievalResult:
        audit_events: list[RetrievalAuditEvent] = []

        if source_url != policy.source_url:
            decision = AccessDecision(
                kind=AccessDecisionKind.DENY,
                reason="source URL does not match retrieval policy",
            )
            event = self._record_event(source_url=source_url, decision=decision, signals=(), attempt=1)
            audit_events.append(event)
            return RetrievalResult(
                source_url=source_url,
                content=None,
                decision=decision,
                audit_events=tuple(audit_events),
            )

        if not policy.authorized:
            decision = AccessDecision(kind=AccessDecisionKind.DENY, reason="policy not authorized")
            event = self._record_event(source_url=source_url, decision=decision, signals=(), attempt=1)
            audit_events.append(event)
            return RetrievalResult(
                source_url=source_url,
                content=None,
                decision=decision,
                audit_events=tuple(audit_events),
            )

        if policy.rate_limit_budget <= 0:
            decision = AccessDecision(
                kind=AccessDecisionKind.RETRY_LATER,
                reason="rate limit budget exhausted",
            )
            event = self._record_event(source_url=source_url, decision=decision, signals=(), attempt=1)
            audit_events.append(event)
            return RetrievalResult(
                source_url=source_url,
                content=None,
                decision=decision,
                audit_events=tuple(audit_events),
            )

        max_attempts = max(1, policy.max_retries + 1)
        attempt = 1
        current_url = source_url
        fallback_used: str | None = None
        remaining_budget = policy.rate_limit_budget

        while attempt <= max_attempts:
            if remaining_budget <= 0:
                decision = AccessDecision(
                    kind=AccessDecisionKind.RETRY_LATER,
                    reason="rate limit budget exhausted",
                )
                event = self._record_event(
                    source_url=current_url,
                    decision=decision,
                    signals=(),
                    attempt=attempt,
                )
                audit_events.append(event)
                return RetrievalResult(
                    source_url=source_url,
                    content=None,
                    decision=decision,
                    audit_events=tuple(audit_events),
                    fallback_used=fallback_used,
                )

            fetched_url = current_url
            outcome: bytes | Exception
            remaining_budget -= 1
            try:
                outcome = self._document_source.fetch(fetched_url)
            except Exception as exc:  # noqa: BLE001 - intentionally capture the outcome object
                outcome = exc

            signals = tuple(self._observer.observe(fetched_url, outcome))
            decision = self._policy_evaluator.evaluate(signals, policy, attempt)

            if decision.kind is AccessDecisionKind.USE_APPROVED_FALLBACK:
                fallback_url = decision.fallback_url or self._first_approved_fallback(policy)
                if (
                    not fallback_url
                    or fallback_url == current_url
                    or fallback_url not in policy.approved_fallback_urls
                ):
                    decision = AccessDecision(
                        kind=AccessDecisionKind.HANDOFF,
                        reason="approved fallback unavailable",
                    )
                else:
                    current_url = fallback_url
                    fallback_used = fallback_url

            event = self._record_event(
                source_url=fetched_url,
                decision=decision,
                signals=signals,
                attempt=attempt,
            )
            audit_events.append(event)

            if decision.kind is AccessDecisionKind.ALLOW and isinstance(outcome, bytes):
                return RetrievalResult(
                    source_url=source_url,
                    content=outcome,
                    decision=decision,
                    audit_events=tuple(audit_events),
                    fallback_used=fallback_used,
                )

            if decision.kind is AccessDecisionKind.USE_APPROVED_FALLBACK:
                continue

            if decision.kind is AccessDecisionKind.RETRY_LATER:
                if attempt < max_attempts:
                    attempt += 1
                    continue
                return RetrievalResult(
                    source_url=source_url,
                    content=None,
                    decision=decision,
                    audit_events=tuple(audit_events),
                    fallback_used=fallback_used,
                )

            if decision.kind in (AccessDecisionKind.HANDOFF, AccessDecisionKind.DENY):
                return RetrievalResult(
                    source_url=source_url,
                    content=None,
                    decision=decision,
                    audit_events=tuple(audit_events),
                    fallback_used=fallback_used,
                )

            if attempt < max_attempts:
                attempt += 1
            else:
                return RetrievalResult(
                    source_url=source_url,
                    content=None,
                    decision=AccessDecision(
                        kind=AccessDecisionKind.RETRY_LATER,
                        reason="retrieval completed without compliant content",
                    ),
                    audit_events=tuple(audit_events),
                    fallback_used=fallback_used,
                )

        return RetrievalResult(
            source_url=source_url,
            content=None,
            decision=AccessDecision(
                kind=AccessDecisionKind.RETRY_LATER,
                reason="retrieval completed without compliant content",
            ),
            audit_events=tuple(audit_events),
            fallback_used=fallback_used,
        )

    def _record_event(
        self,
        *,
        source_url: str,
        decision: AccessDecision,
        signals: Sequence[AccessSignal],
        attempt: int,
    ) -> RetrievalAuditEvent:
        event = RetrievalAuditEvent(
            source_url=source_url,
            decision=decision,
            signals=tuple(signals),
            attempt=attempt,
            timestamp=datetime.now(timezone.utc),
        )
        self._auditor.record(event)
        return event

    @staticmethod
    def _first_approved_fallback(policy: RetrievalPolicy) -> str | None:
        return policy.approved_fallback_urls[0] if policy.approved_fallback_urls else None

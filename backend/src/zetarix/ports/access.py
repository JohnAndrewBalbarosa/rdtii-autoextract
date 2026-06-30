"""Access ports for compliance, observability, and handoff orchestration.

Concrete implementations observe retrieval outcomes, evaluate policy, and persist
audit events at the edge. The core depends on these interfaces only.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from zetarix.domain.access import (
    AccessDecision,
    AccessSignal,
    RetrievalAuditEvent,
    RetrievalPolicy,
)


class AccessObserver(Protocol):
    """Observes retrieval outcomes and emits compliance signals."""

    def observe(self, source_url: str, outcome: object) -> list[AccessSignal]: ...


class AccessPolicyEvaluator(Protocol):
    """Evaluates signals against policy and returns a retrieval decision."""

    def evaluate(
        self,
        signals: Sequence[AccessSignal],
        policy: RetrievalPolicy,
        attempt: int,
    ) -> AccessDecision: ...


class RetrievalAuditor(Protocol):
    """Records retrieval audit events for compliance and operational review."""

    def record(self, event: RetrievalAuditEvent) -> None: ...

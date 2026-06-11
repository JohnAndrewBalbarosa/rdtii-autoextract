"""Access domain entities for compliance, observability, and handoff.

These are framework-agnostic value objects for modeling retrieval access signals,
policy decisions, audit events, and outcomes. No adapter, transport, or crawler
implementation belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AccessLayer(Enum):
    """OSI-style layer for access and retrieval observability."""

    NETWORK = "network"
    SESSION = "session"
    APPLICATION = "application"
    USER_PROCESS = "user_process"
    MANAGED_DEVICE = "managed_device"


class AccessSignalSeverity(Enum):
    """Severity for access signals emitted by observers."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AccessDecisionKind(Enum):
    """Policy decision kinds for compliant retrieval handling."""

    ALLOW = "allow"
    RETRY_LATER = "retry_later"
    USE_APPROVED_FALLBACK = "use_approved_fallback"
    HANDOFF = "handoff"
    DENY = "deny"


@dataclass(frozen=True)
class AccessSignal:
    """Observed access signal for compliance review and operational handoff."""

    layer: AccessLayer
    source_url: str
    status: str
    detail: str
    severity: AccessSignalSeverity
    timestamp: datetime


@dataclass(frozen=True)
class RetrievalPolicy:
    """Approved retrieval policy governing retries and fallback selection."""

    source_url: str
    authorized: bool
    rate_limit_budget: int
    max_retries: int
    approved_fallback_urls: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True)
class AccessDecision:
    """Policy decision produced from access signals and retrieval policy."""

    kind: AccessDecisionKind
    reason: str
    retry_after_seconds: int | None = None
    fallback_url: str | None = None


@dataclass(frozen=True)
class RetrievalAuditEvent:
    """Immutable audit event for compliant retrieval tracing."""

    source_url: str
    decision: AccessDecision
    signals: tuple[AccessSignal, ...]
    attempt: int
    timestamp: datetime


@dataclass(frozen=True)
class RetrievalResult:
    """Retrieval outcome with content, decision, and audit trail."""

    source_url: str
    content: bytes | None
    decision: AccessDecision
    audit_events: tuple[RetrievalAuditEvent, ...]
    fallback_used: str | None = None

# Compliant Automation Guide

This guide defines a compliance-first automation pattern for lawful retrieval and processing. It is written for future contributors and AI coding agents that need a clear boundary between permitted automation and prohibited bypass/evasion behavior.

## Scope

Use automation only for workflows that are authorized, contractually permitted, and technically bounded by the target system's published interfaces, credentials, and rate policies.

Primary goals:

- Retrieve data lawfully through approved channels.
- Preserve provenance for every record, transform, and decision.
- Fail safely under uncertainty, rate pressure, or policy ambiguity.
- Escalate to a human when authorization, identity, or intent is unclear.

## Reference Architecture

Recommended layers:

1. Ingress and policy gate
1. Retrieval adapter
1. Normalization and validation core
1. Persistence and provenance store
1. Retry and fallback coordinator
1. Human handoff channel
1. Audit and observability pipeline

Design rules:

- Keep policy decisions deterministic and centralized.
- Keep side effects behind adapters.
- Keep parsing, validation, and transformation in pure core modules.
- Keep external calls isolated at the edges.

## Compliance Controls

### Authorization

- Verify the caller, account, and scope before any retrieval.
- Bind each job to an explicit authority statement or ticket.
- Reject ambiguous or unverified requests.

### Retrieval

- Prefer official APIs, export endpoints, feeds, or other documented interfaces.
- Respect published terms, quotas, and tenant boundaries.
- Record source identifiers, timestamps, request parameters, and response status.

### Provenance

- Attach provenance metadata to every artifact and derived output.
- Preserve source URI, fetch time, adapter version, policy version, and transformation hash.
- Distinguish raw input from normalized output.

### Rate Limiting

- Apply client-side rate limits before dispatch.
- Use token buckets or fixed windows with explicit budgets per source and job.
- Treat server throttling as a compliance signal, not an error to defeat.

### Retries

- Retry only for transient failures that are safe to repeat.
- Use bounded attempts, exponential backoff, and jitter.
- Never retry on authorization failures, policy denials, or invalid credentials.

### Fallbacks

- Prefer degraded but compliant behavior over aggressive recovery.
- Fall back to cached, local, or previously approved data only when freshness requirements allow it.
- Mark fallback outputs clearly so downstream consumers can distinguish them from live retrievals.

### Human Handoff

- Escalate when consent, authorization, account state, or source policy is uncertain.
- Escalate when the system detects repeated throttling, inconsistent identity signals, or schema drift that affects correctness.
- Provide a compact review packet: request summary, source, evidence, failure mode, and recommended action.

## Observability Abstraction

Use OSI-style layers as an observability model only. Do not treat these layers as a basis for evasion, stealth, or bypass.

### 1. Network

- Observe request volume, latency, error classes, and server responses.
- Track endpoint, status, transport errors, and retry outcomes.

### 2. Session / Transport

- Observe authenticated session state, token freshness, cookie expiry, TLS errors, and connection reuse.
- Detect session invalidation and re-authentication events.

### 3. Application

- Observe request intent, API method, payload shape, validation errors, and business-rule denials.
- Log policy checks and normalization outcomes.

### 4. User / Process

- Observe which user, service account, or process initiated the job.
- Record job IDs, command origins, and approval references.

### 5. Managed-Device Context

- If applicable and explicitly authorized, record managed-device posture such as approved host identity, environment labels, and compliance status.
- Keep this metadata for audit and routing only.

## Out of Scope

The following are prohibited and must not be implemented, suggested, or optimized:

- CAPTCHA bypass.
- Fingerprint spoofing.
- Proxy/IP evasion.
- MAC spoofing.
- Cell-tower manipulation.
- Unauthorized device or hardware access.

If a workflow appears to require any of the above, stop and route to a human for review.

## Clean-Code Guidelines

For future contributors and AI agents:

- Use single-responsibility modules.
- Define ports/adapters boundaries explicitly.
- Keep domain logic independent of transport and persistence.
- Prefer typed interfaces for inputs, outputs, and policy decisions.
- Keep pure core logic deterministic and side-effect free.
- Centralize audit logging at the boundary layer.
- Make failure modes explicit in types and return values.
- Avoid hidden global state, implicit retries, and ad hoc policy checks.

## Implementation Conventions

- Put policy evaluation in a small deterministic module.
- Put source-specific behavior in adapters that can be swapped without changing the core.
- Normalize all inbound data before storage or downstream use.
- Emit structured audit events for every request, decision, retry, fallback, and handoff.
- Make compliance checks testable with unit tests and fixture-based integration tests.

## AI-Coding Guidelines

When an AI coding agent modifies this system:

- Prefer minimal, localized changes.
- Preserve existing audit and provenance semantics.
- Do not weaken authorization, throttling, or handoff logic.
- Do not introduce hidden retries, background scraping, or stealth features.
- Keep policy code reviewable and deterministic.
- Add tests for every new branch that affects compliance behavior.

## Operational Checklist

- Authorized source and scope confirmed.
- Retrieval method is documented and permitted.
- Rate limit budget is defined.
- Retry policy is bounded.
- Provenance fields are emitted.
- Fallback behavior is explicit.
- Human handoff path is available.
- Audit records are searchable and retained.

## Summary

The system should automate lawful retrieval, not circumvent controls. If a requirement cannot be satisfied without bypassing protections or violating source policy, the correct response is to stop, log the issue, and escalate for human review.

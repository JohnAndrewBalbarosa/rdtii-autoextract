"""RDTII indicator-code translation — canonical ``P6-I1`` ⇔ golden-DB ``6.1``.

Two formats coexist in the system:

* **Canonical / submission** form ``P{pillar}-I{number}`` (e.g. ``P6-I1``) — what the
  Round-1 output CSV requires (``docs/ROUND1_SUBMISSION_SPEC.md`` p.14) and what a
  ``Finding.indicator`` carries.
* **Golden-DB** form ``{pillar}.{number}`` (e.g. ``6.1``) — how the ESCAP workbooks and
  ``core/pipeline/golden_dataset.GoldRecord`` store the indicator id.

These helpers are pure (no I/O, no framework imports) so scoring can normalise both
sides to a single key before comparing. A trailing lowercase letter (sub-indicator,
e.g. ``6.1a`` / ``P6-I1a``) is preserved through the round-trip.

The map rule: ``P{p}-I{n}`` ⇔ ``{p}.{n}``.
"""

from __future__ import annotations

import re

# Canonical: P6-I1, P6-I1a (optional trailing sub-indicator letter).
_CANONICAL_RE = re.compile(r"^P(?P<pillar>\d+)-I(?P<number>\d+)(?P<suffix>[a-z]?)$")
# DB / dotted: 6.1, 6.1a.
_DB_RE = re.compile(r"^(?P<pillar>\d+)\.(?P<number>\d+)(?P<suffix>[a-z]?)$")


def _parse(code: str) -> tuple[int, int, str]:
    """Parse either accepted form → (pillar, number, suffix). Raise on malformed input."""
    if not isinstance(code, str):
        raise ValueError(f"indicator code must be a string, got {type(code).__name__}")
    cleaned = code.strip()
    if not cleaned:
        raise ValueError("indicator code is empty")
    match = _DB_RE.match(cleaned) or _CANONICAL_RE.match(cleaned)
    if match is None:
        raise ValueError(f"malformed indicator code: {code!r}")
    return int(match["pillar"]), int(match["number"]), match["suffix"]


def to_canonical(code: str) -> str:
    """Normalise any accepted form to ``P{p}-I{n}`` (e.g. ``6.1`` / ``" 6.1 "`` → ``P6-I1``).

    A trailing sub-indicator letter is preserved: ``6.1a`` → ``P6-I1a``.
    Raises ``ValueError`` on malformed input.
    """
    pillar, number, suffix = _parse(code)
    return f"P{pillar}-I{number}{suffix}"


def to_db(code: str) -> str:
    """Normalise any accepted form to the golden-DB dotted form (``P6-I1`` → ``6.1``).

    Raises ``ValueError`` on malformed input.
    """
    pillar, number, suffix = _parse(code)
    return f"{pillar}.{number}{suffix}"


def pillar_of(code: str) -> int:
    """Return the pillar number from any accepted form (``P6-I1`` / ``6.1`` → ``6``).

    Raises ``ValueError`` on malformed input.
    """
    pillar, _number, _suffix = _parse(code)
    return pillar

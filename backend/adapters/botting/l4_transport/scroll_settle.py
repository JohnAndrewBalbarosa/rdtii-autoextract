"""Condition-based scroll/expand settling for lazy-rendering SPA law portals.

Portals like legislation.gov.au render provision text incrementally as the page is
scrolled (the reproduced curve: innerText 1261 → 3761 → 8356 → 16094 → plateau). A fixed
``wait_for_timeout`` either stops too early (truncated statute) or wastes time. Instead we
scroll + expand in rounds and stop once the visible text length has plateaued for a few
consecutive checks.

``is_settled`` is the pure stop rule (unit-tested). ``settle_page`` is the thin Playwright
driver that applies it to a live page.
"""

from __future__ import annotations

# Best-effort JS to open collapsed legal content (accordions / "Expand all" toggles).
EXPAND_JS = """() => {
    const fire = (el) => { try { el.click(); } catch (_) {} };
    document.querySelectorAll('button, a, [role=button]').forEach((b) => {
        const t = (b.textContent || '').trim().toLowerCase();
        if (t === 'expand all' || t === 'expand' || t.startsWith('expand ') ||
            t === 'show all' || t === 'open all') fire(b);
    });
    document.querySelectorAll('[aria-expanded="false"]').forEach(fire);
}"""

_DEFAULT_PATIENCE = 2
_DEFAULT_MAX_ROUNDS = 12
_DEFAULT_PAUSE_MS = 1000
_DEFAULT_EPSILON = 8  # chars; growth at/below this is treated as noise, not new content


def is_settled(lengths: list[int], patience: int = _DEFAULT_PATIENCE, epsilon: int = _DEFAULT_EPSILON) -> bool:
    """True when the last ``patience`` measurements show no real growth (≤ epsilon).

    Needs at least ``patience + 1`` samples so an initial measurement plus ``patience``
    flat follow-ups are required before declaring the page done loading.
    """
    if len(lengths) < patience + 1:
        return False
    recent = lengths[-(patience + 1):]
    return all(later - earlier <= epsilon for earlier, later in zip(recent, recent[1:]))


def settle_page(
    page,
    *,
    patience: int = _DEFAULT_PATIENCE,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    pause_ms: int = _DEFAULT_PAUSE_MS,
    on_round=None,
) -> list[int]:
    """Scroll + expand a live Playwright page until its visible text plateaus.

    Returns the recorded innerText-length history. ``on_round(round_no, length)`` is an
    optional callback (used by the debugger to update its panel). All browser calls are
    best-effort; a failing evaluate ends the loop rather than raising.
    """
    lengths: list[int] = []
    for round_no in range(max_rounds):
        try:
            page.evaluate(EXPAND_JS)
            page.evaluate("() => window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(pause_ms)
            length = int(page.evaluate("() => document.body.innerText.length"))
        except Exception:
            break
        lengths.append(length)
        if on_round is not None:
            on_round(round_no + 1, length)
        if is_settled(lengths, patience=patience):
            break
    return lengths

"""Tests for condition-based scroll-settle decision logic.

The driver scrolls + expands a live SPA until lazy-rendered provision text stops
growing. The *decision* (keep scrolling vs. settled) is a pure function so the
robustness rule is unit-tested without a browser. Replaces the old fixed
``wait_for_timeout`` guessing with an evidence-based stop.
"""

from __future__ import annotations

from adapters.botting.l4_transport.scroll_settle import is_settled


def test_not_settled_while_growing():
    assert is_settled([1261, 3761, 8356], patience=2) is False


def test_settled_after_patience_plateau():
    # Matches the reproduced legislation.gov.au curve: grows then plateaus.
    assert is_settled([1261, 3761, 8356, 16094, 16094, 16094], patience=2) is True


def test_one_flat_check_not_enough_for_patience_two():
    assert is_settled([8356, 16094, 16094], patience=2) is False


def test_needs_minimum_history():
    assert is_settled([16094], patience=2) is False
    assert is_settled([], patience=2) is False


def test_tiny_growth_below_epsilon_counts_as_flat():
    # A handful of whitespace chars is not real new content.
    assert is_settled([16094, 16096, 16098], patience=2, epsilon=8) is True

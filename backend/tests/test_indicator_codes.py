"""Unit tests for indicator-code translation (canonical ``P6-I1`` ⇔ DB ``6.1``)."""

from __future__ import annotations

import pytest

from core.domain.indicator_codes import pillar_of, to_canonical, to_db


# --- to_canonical ---

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6.1", "P6-I1"),
        ("P6-I1", "P6-I1"),
        (" 6.1 ", "P6-I1"),
        ("7.12", "P7-I12"),
        ("P7-I12", "P7-I12"),
        ("6.1a", "P6-I1a"),  # sub-indicator letter preserved
        ("P6-I1a", "P6-I1a"),
    ],
)
def test_to_canonical_normalises_both_forms(raw, expected):
    assert to_canonical(raw) == expected


# --- to_db ---

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("P6-I1", "6.1"),
        ("6.1", "6.1"),
        ("P7-I12", "7.12"),
        ("P6-I1a", "6.1a"),  # sub-indicator letter preserved
        (" P6-I1 ", "6.1"),
    ],
)
def test_to_db_normalises_both_forms(raw, expected):
    assert to_db(raw) == expected


# --- round-trips ---

@pytest.mark.parametrize("db", ["6.1", "7.5", "7.12", "6.1a"])
def test_db_canonical_round_trip(db):
    assert to_db(to_canonical(db)) == db


@pytest.mark.parametrize("canonical", ["P6-I1", "P7-I5", "P7-I12", "P6-I1a"])
def test_canonical_db_round_trip(canonical):
    assert to_canonical(to_db(canonical)) == canonical


# --- pillar_of ---

@pytest.mark.parametrize(
    "code,pillar",
    [("6.1", 6), ("P6-I1", 6), ("7.12", 7), ("P7-I12", 7), ("6.1a", 6)],
)
def test_pillar_of(code, pillar):
    assert pillar_of(code) == pillar


# --- malformed input ---

@pytest.mark.parametrize(
    "junk",
    ["", "   ", "P6", "6", "6.", "P6-I", "abc", "6,1", "P6_I1", "6.1.2", "PA-IB"],
)
def test_malformed_raises_value_error(junk):
    with pytest.raises(ValueError):
        to_canonical(junk)
    with pytest.raises(ValueError):
        to_db(junk)
    with pytest.raises(ValueError):
        pillar_of(junk)


def test_non_string_raises_value_error():
    with pytest.raises(ValueError):
        to_canonical(None)  # type: ignore[arg-type]

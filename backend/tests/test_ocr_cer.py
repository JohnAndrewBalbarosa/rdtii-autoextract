"""Tests for core/pipeline/ocr_cer.py — CER measurement harness."""

from __future__ import annotations

import pytest

from core.pipeline.ocr_cer import CerReport, cer, measure_cer


# ---------------------------------------------------------------------------
# cer() — unit tests
# ---------------------------------------------------------------------------

class TestCerIdentical:
    def test_identical_strings_return_zero(self) -> None:
        assert cer("hello world", "hello world") == 0.0

    def test_identical_empty_strings_return_zero(self) -> None:
        assert cer("", "") == 0.0

    def test_identical_long_string_return_zero(self) -> None:
        text = "a" * 500
        assert cer(text, text) == 0.0


class TestCerEmptyEdgeCases:
    def test_both_empty_returns_zero(self) -> None:
        assert cer("", "") == 0.0

    def test_empty_reference_nonempty_hypothesis_returns_one(self) -> None:
        assert cer("", "some text") == 1.0

    def test_nonempty_reference_empty_hypothesis(self) -> None:
        # All characters deleted → distance == len(reference)
        ref = "hello"
        result = cer(ref, "")
        assert result == pytest.approx(1.0)


class TestCerSingleSubstitution:
    def test_one_substitution_in_100_char_string(self) -> None:
        ref = "a" * 100
        hyp = "a" * 99 + "b"   # one substitution at position 99
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(0.01, abs=1e-9)

    def test_one_insertion_in_100_char_string(self) -> None:
        ref = "a" * 100
        hyp = "a" * 100 + "b"  # one insertion
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(0.01, abs=1e-9)

    def test_one_deletion_in_100_char_string(self) -> None:
        ref = "a" * 100
        hyp = "a" * 99         # one deletion
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(0.01, abs=1e-9)


class TestCerMultipleEdits:
    def test_completely_different_strings(self) -> None:
        ref = "abc"
        hyp = "xyz"
        # 3 substitutions over length 3 → 1.0
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(1.0)

    def test_partial_overlap(self) -> None:
        ref = "abcde"
        hyp = "abcXX"   # 2 substitutions out of 5
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(2 / 5)

    def test_insertions_and_deletions_mixed(self) -> None:
        # ref "kitten" → hyp "sitting": classic Levenshtein = 3 edits
        result = cer("kitten", "sitting", normalize=False)
        assert result == pytest.approx(3 / 6)


class TestCerWhitespaceNormalization:
    def test_leading_trailing_whitespace_ignored(self) -> None:
        assert cer("  hello  ", "hello") == 0.0

    def test_multiple_spaces_collapsed(self) -> None:
        assert cer("hello   world", "hello world") == 0.0

    def test_tabs_and_newlines_collapsed(self) -> None:
        assert cer("hello\t\nworld", "hello world") == 0.0

    def test_normalize_false_preserves_whitespace(self) -> None:
        # With normalize=False, extra space counts as 1 extra char
        ref = "ab"
        hyp = "a b"
        result = cer(ref, hyp, normalize=False)
        assert result == pytest.approx(1 / 2)


# ---------------------------------------------------------------------------
# measure_cer() — batch + CerReport
# ---------------------------------------------------------------------------

class TestMeasureCerEmptySamples:
    def test_empty_list_returns_zero_mean_and_passed(self) -> None:
        report = measure_cer([])
        assert report.mean_cer == 0.0
        assert report.passed is True
        assert report.n_samples == 0
        assert report.per_sample == ()


class TestMeasureCerSyntheticPass:
    """A sample set whose mean CER is well below 0.05 → passed=True."""

    _SAMPLES: list[tuple[str, str]] = [
        ("The quick brown fox", "The quick brown fox"),   # 0.0
        ("a" * 100, "a" * 99 + "b"),                     # 0.01
        ("hello world", "hello world"),                   # 0.0
        ("regulatory document", "regulatory document"),   # 0.0
    ]

    def test_passed_is_true(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert report.passed is True

    def test_mean_cer_below_threshold(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert report.mean_cer < 0.05

    def test_n_samples_correct(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert report.n_samples == 4

    def test_per_sample_length_matches(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert len(report.per_sample) == 4

    def test_report_is_frozen(self) -> None:
        report = measure_cer(self._SAMPLES)
        with pytest.raises((AttributeError, TypeError)):
            report.mean_cer = 0.99  # type: ignore[misc]


class TestMeasureCerSyntheticFail:
    """A sample set whose mean CER exceeds 0.05 → passed=False."""

    _SAMPLES: list[tuple[str, str]] = [
        ("abcdefghij", "ABCDEFGHIJ"),   # 10 subs / 10 → 1.0
        ("hello", "world"),             # 4 edits / 5 → 0.8
        ("perfect match", "perfect match"),  # 0.0
    ]

    def test_passed_is_false(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert report.passed is False

    def test_mean_cer_above_threshold(self) -> None:
        report = measure_cer(self._SAMPLES)
        assert report.mean_cer > 0.05


class TestMeasureCerCustomThreshold:
    def test_custom_threshold_respected(self) -> None:
        samples = [("abc", "abd")]  # 1/3 ≈ 0.333
        report_strict = measure_cer(samples, threshold=0.30)
        report_loose = measure_cer(samples, threshold=0.40)
        assert report_strict.passed is False
        assert report_loose.passed is True


class TestCerReportType:
    def test_cer_report_is_dataclass(self) -> None:
        report = measure_cer([("hello", "hello")])
        assert isinstance(report, CerReport)

    def test_per_sample_is_tuple(self) -> None:
        report = measure_cer([("abc", "abc"), ("xyz", "xyz")])
        assert isinstance(report.per_sample, tuple)

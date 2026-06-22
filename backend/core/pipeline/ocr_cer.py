"""OCR Character Error Rate (CER) measurement harness.

CER = Levenshtein_edit_distance(reference, hypothesis) / max(1, len(reference))

A CER of 0.0 means perfect; < 0.05 (5%) is the Round-1 rubric target (R17).

OCR adapter wiring
------------------
No concrete OCR adapter (e.g. Tesseract, PaddleOCR, Google Vision) is wired in
this environment — only the ``OCREngine`` Protocol exists in ``core/ports``.
The ``measure_adapter_cer`` function is provided for when a real adapter is
available.  To actually *prove* the < 5% CER claim you need:

1. A configured ``OCREngine`` implementation (e.g. ``adapters/ocr/tesseract_adapter.py``).
2. A representative corpus of scanned regulatory PDFs (Singapore PDPC, AGC, etc.)
   with corresponding gold-standard reference transcripts.
3. Call ``measure_adapter_cer(engine, [(path, reference), ...])`` and verify the
   returned ``CerReport.passed`` is ``True`` and ``mean_cer < 0.05``.

Until those exist the ``cer`` / ``measure_cer`` machinery is fully testable with
synthetic string pairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports import OCREngine


# ---------------------------------------------------------------------------
# Core metric
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Collapse whitespace runs and strip leading/trailing whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def _levenshtein(a: str, b: str) -> int:
    """Two-row O(n) Levenshtein edit distance (insertions, deletions, substitutions)."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m

    # prev[j] = distance(a[:0], b[:j]), curr is built each row
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev

    return prev[n]


def cer(reference: str, hypothesis: str, *, normalize: bool = True) -> float:
    """Character Error Rate between *reference* and *hypothesis*.

    Parameters
    ----------
    reference:
        Gold-standard (human-verified) text.
    hypothesis:
        OCR-produced text being evaluated.
    normalize:
        When ``True`` (default) collapse whitespace runs and strip ends before
        comparing.  Prevents benign formatting differences from inflating CER.

    Returns
    -------
    float
        ``edit_distance / max(1, len(reference))`` after optional normalisation.
        Returns ``0.0`` when both strings are empty; ``1.0`` (capped) when
        reference is empty but hypothesis is non-empty.
    """
    if normalize:
        reference = _normalize(reference)
        hypothesis = _normalize(hypothesis)

    ref_len = len(reference)
    hyp_len = len(hypothesis)

    if ref_len == 0 and hyp_len == 0:
        return 0.0
    if ref_len == 0:
        # Anything produced from nothing is a 100 % error
        return 1.0

    dist = _levenshtein(reference, hypothesis)
    return dist / ref_len


# ---------------------------------------------------------------------------
# Batch measurement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CerReport:
    """Immutable summary of a CER evaluation run."""

    mean_cer: float
    per_sample: tuple[float, ...]
    n_samples: int
    passed: bool  # mean_cer < threshold


def measure_cer(
    samples: list[tuple[str, str]],
    threshold: float = 0.05,
) -> CerReport:
    """Compute CER for each ``(reference_text, ocr_text)`` pair.

    Parameters
    ----------
    samples:
        List of ``(reference, hypothesis)`` string pairs.
    threshold:
        Pass/fail boundary.  Default ``0.05`` matches the Round-1 rubric.

    Returns
    -------
    CerReport
        Frozen dataclass with mean CER, per-sample CERs, sample count, and
        whether the mean is below the threshold.
    """
    if not samples:
        return CerReport(mean_cer=0.0, per_sample=(), n_samples=0, passed=True)

    per = tuple(cer(ref, hyp) for ref, hyp in samples)
    mean = sum(per) / len(per)
    return CerReport(
        mean_cer=mean,
        per_sample=per,
        n_samples=len(per),
        passed=mean < threshold,
    )


# ---------------------------------------------------------------------------
# OCR adapter wiring (machinery-only until a real adapter is registered)
# ---------------------------------------------------------------------------

def measure_adapter_cer(
    ocr_engine: "OCREngine",
    samples: list[tuple[str, str]],
    threshold: float = 0.05,
) -> CerReport:
    """Run *ocr_engine* on each input path and measure CER vs. reference texts.

    Parameters
    ----------
    ocr_engine:
        Any object satisfying ``core.ports.OCREngine`` Protocol (has
        ``extract(raw: bytes) -> str``).
    samples:
        List of ``(file_path_or_url, reference_text)`` pairs.  Each path is
        opened in binary mode and passed to ``ocr_engine.extract()``.
    threshold:
        Pass/fail boundary.

    Returns
    -------
    CerReport
        Same shape as ``measure_cer`` but driven by actual OCR output.

    Raises
    ------
    FileNotFoundError
        If a path in *samples* does not exist on disk.
    """
    string_pairs: list[tuple[str, str]] = []
    for path, reference in samples:
        with open(path, "rb") as fh:
            raw = fh.read()
        hypothesis = ocr_engine.extract(raw)
        string_pairs.append((reference, hypothesis))
    return measure_cer(string_pairs, threshold=threshold)

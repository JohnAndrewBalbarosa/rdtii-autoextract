"""Deterministic, no-LLM metrics for the Zetarix scraper — measurable today.

Complements the token benchmarks with quantitative signals that need no live model:
  1. DOM compression   — raw HTML -> cleaned text -> layout skeleton (tiktoken cl100k_base)
  2. Throughput        — deterministic per-page work (fingerprint + clean), ms/page & pages/s
  3. Fingerprint       — stability under volatile-class noise + cross-page collision count
  4. Contamination     — boilerplate terms surviving into cleaned output

    python benchmarks/quality_metrics.py --output benchmarks/results/quality_metrics.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tiktoken  # noqa: E402

from zetarix.cleaning.dom_cleaner import DomCleaner  # noqa: E402
from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, _BOILERPLATE  # noqa: E402

_ENC = tiktoken.get_encoding("cl100k_base")
_FIXTURES = ("benchmarks/data/inspect_au.html", "benchmarks/data/walkthrough_au.html", "test_law.html")
_VOLATILE_NOISE = ("active", "selected", "current", "page-1", "page-2", "page-7", "is-open")
_REPS = 30


def _toks(value: str) -> int:
    return len(_ENC.encode(value))


def _fp(html: str) -> str:
    return AdaptiveDomainCrawler(object(), object(), robots_allowed=lambda *_: True)._layout_fingerprint(html)[0]


def _inject_volatile(html: str, marker: str) -> str:
    """Add sibling-state volatile classes to every classed element (simulates page N)."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(True):
        if el.get("class"):
            el["class"] = list(el.get("class")) + [marker]
    return str(soup)


def _compression(html: str) -> dict:
    cleaned = DomCleaner().clean_html(html)
    skeleton = AdaptiveDomainCrawler._sample("https://x.gov/p", html)["html_excerpt"]
    raw_t, clean_t, skel_t = _toks(html), _toks(cleaned), _toks(skeleton)
    return {
        "raw_html_tokens": raw_t,
        "cleaned_text_tokens": clean_t,
        "skeleton_tokens": skel_t,
        "cleaned_reduction_pct": round(100 * (1 - clean_t / raw_t), 1) if raw_t else 0,
        "skeleton_reduction_pct": round(100 * (1 - skel_t / raw_t), 1) if raw_t else 0,
    }


def _throughput(html: str) -> dict:
    cleaner = DomCleaner()
    crawler = AdaptiveDomainCrawler(object(), object(), robots_allowed=lambda *_: True)
    samples = []
    for _ in range(_REPS):
        t0 = time.perf_counter()
        crawler._layout_fingerprint(html)
        cleaner.clean_html(html)
        samples.append((time.perf_counter() - t0) * 1000)
    median_ms = round(statistics.median(samples), 2)
    return {"median_ms_per_page": median_ms, "pages_per_sec": round(1000 / median_ms, 1) if median_ms else None}


def _contamination(html: str) -> dict:
    cleaned = DomCleaner().clean_html(html).lower()
    hits = {term: cleaned.count(term) for term in _BOILERPLATE if term in cleaned}
    return {"boilerplate_terms_found": hits, "contaminated": bool(hits)}


def run(output_path: Path) -> dict:
    base = Path.cwd()
    per_fixture = {}
    fingerprints = {}
    for rel in _FIXTURES:
        p = base / rel
        if not p.exists():
            per_fixture[rel] = {"error": "missing"}
            continue
        html = p.read_text(encoding="utf-8")
        # fingerprint stability under volatile-class noise
        base_fp = _fp(html)
        variants = [_fp(_inject_volatile(html, m)) for m in _VOLATILE_NOISE]
        stable = sum(1 for v in variants if v == base_fp)
        per_fixture[rel] = {
            "compression": _compression(html),
            "throughput": _throughput(html),
            "contamination": _contamination(html),
            "fingerprint_stability": {
                "noise_variants": len(variants),
                "kept_same_fingerprint": stable,
                "stability_pct": round(100 * stable / len(variants), 1),
            },
        }
        fingerprints[rel] = base_fp

    distinct = len(set(fingerprints.values()))
    report = {
        "measurement": {"kind": "deterministic_no_llm", "encoding": "cl100k_base", "timing_reps": _REPS},
        "per_fixture": per_fixture,
        "fingerprint_collision": {
            "distinct_fixtures": len(fingerprints),
            "distinct_fingerprints": distinct,
            "collisions": len(fingerprints) - distinct,
            "fingerprints": fingerprints,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/quality_metrics.json"))
    args = parser.parse_args(argv)
    report = run(args.output)
    for rel, m in report["per_fixture"].items():
        if "error" in m:
            print(f"{rel}: MISSING")
            continue
        c, t = m["compression"], m["throughput"]
        print(f"{rel}: raw={c['raw_html_tokens']} -> cleaned -{c['cleaned_reduction_pct']}% "
              f"-> skeleton -{c['skeleton_reduction_pct']}% | {t['median_ms_per_page']}ms/pg "
              f"({t['pages_per_sec']} pg/s) | stability {m['fingerprint_stability']['stability_pct']}% "
              f"| contaminated={m['contamination']['contaminated']}")
    fc = report["fingerprint_collision"]
    print(f"fingerprint collision: {fc['collisions']} ({fc['distinct_fingerprints']}/{fc['distinct_fixtures']} distinct)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

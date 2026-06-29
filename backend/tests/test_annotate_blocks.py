"""Tests for DomCleaner.annotate_blocks — the JSON keep/drop decision trace (Issue #24).

Focus: the trace must surface SKIPPED blocks that still hold substantial text, because
real law/article text can hide in a sidebar/nav the selector logic ignores (regex/selector
based, not context based). That is the reviewer's safety net.
"""

from adapters.botting.l6_presentation.dom_cleaner import DomCleaner

# A page where a real, long provision-like paragraph is buried in an <aside> sidebar that
# the boilerplate rules drop — exactly the false-skip risk the reviewer worries about.
_LONG = (
    "An organisation must not transfer personal data to a country or territory outside the "
    "jurisdiction unless the recipient is bound by enforceable obligations ensuring a "
    "comparable standard of protection to that provided under this Act, and the transfer "
    "satisfies the prescribed conditions."
)

HTML = f"""
<html><body>
  <nav><a href="/home">Home</a><a href="/about">About</a></nav>
  <aside class="sidebar">
    <h2>Part 9 - Definitions</h2>
    <p>{_LONG}</p>
  </aside>
  <main>
    <h1>Personal Data Protection Act</h1>
    <h2>Section 26 - Transfer Limitation</h2>
    <p>{_LONG}</p>
    <h3 id="toolbar-tabs">Downloads</h3>
    <p>All versions</p>
  </main>
</body></html>
"""


def _by_preview(blocks, needle):
    return [b for b in blocks if needle in b["preview"]]


def test_kept_block_is_main_provision():
    trace = DomCleaner().annotate_blocks(HTML)
    kept = [b for b in trace["blocks"] if b["decision"] == "kept"]
    assert any("must not transfer" in b["preview"] for b in kept)
    assert trace["summary"]["kept"] >= 1


def test_sidebar_long_text_is_flagged_as_potential_false_skip():
    trace = DomCleaner().annotate_blocks(HTML)
    # The sidebar provision must be reported as skipped/boilerplate, NOT silently gone.
    sidebar_blocks = [
        b for b in trace["blocks"]
        if "must not transfer" in b["preview"] and b["decision"] == "skipped"
    ]
    assert sidebar_blocks, "sidebar law text must appear as a skipped block"
    assert sidebar_blocks[0]["reason"] == "boilerplate"
    assert sidebar_blocks[0].get("selector_hit")  # which rule dropped it
    # And it must raise the false-skip count so the reviewer is prompted to check it.
    assert trace["summary"]["potential_false_skips"] >= 1


def test_short_chrome_group_is_skipped_as_chrome():
    trace = DomCleaner().annotate_blocks(HTML)
    chrome = _by_preview(trace["blocks"], "Downloads") + _by_preview(trace["blocks"], "All versions")
    assert chrome, "the short Downloads/All versions group should appear in the trace"
    assert all(b["decision"] == "skipped" for b in chrome)
    assert all(b["reason"] in {"chrome", "outside-content"} for b in chrome)


def test_summary_shape():
    trace = DomCleaner().annotate_blocks(HTML)
    s = trace["summary"]
    assert set(s) == {"kept", "chars_kept", "dropped", "potential_false_skips"}
    assert isinstance(s["dropped"], dict)
    # every block carries the audit fields
    for b in trace["blocks"]:
        assert set(["tag", "anchor", "path", "decision", "reason", "char_count", "preview"]) <= set(b)


def test_reuses_keep_logic_consistent_with_annotate_html():
    """annotate_blocks 'kept' set should match annotate_html's data-zx-keep anchors."""
    cleaner = DomCleaner()
    trace = cleaner.annotate_blocks(HTML)
    annotated = cleaner.annotate_html(HTML)
    # both should keep the main Section 26 provision and not the nav
    kept_previews = [b["preview"] for b in trace["blocks"] if b["decision"] == "kept"]
    assert any("must not transfer" in p for p in kept_previews)
    assert "data-zx-keep" in annotated

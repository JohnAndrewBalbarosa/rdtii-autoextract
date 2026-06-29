"""Bug #2 fix: collapsed list-of-provisions pages must split into per-section sections.

Mirrors legislation.gov.au: provisions are <li> with a section-number prefix ("1  Short
title", "2A  Objects"), wrapped by "Collapse Part …" aggregate <li> that duplicate child
text, with the Act title in the masthead (outside the content area). Aligned design:
  - split on section-number <li> (regex fallback) -> one section each
  - Part/Division aggregate -> parent breadcrumb path, drop duplicated body
  - Act title -> root of the breadcrumb path
"""

from adapters.botting.l6_presentation.dom_cleaner import DomCleaner

NESTED = """
<html><body>
  <header><h1>Privacy Act 1988 No. 119, 1988</h1></header>
  <main id="content">
    <h1>Legislation text</h1>
    <ul>
      <li>Collapse Part I-Preliminary
        <ul>
          <li>1  Short title</li>
          <li>2  Commencement</li>
          <li>2A  Objects of this Act</li>
        </ul>
      </li>
      <li>Collapse Part II-Interpretation
        <ul>
          <li>6  Interpretation</li>
        </ul>
      </li>
    </ul>
  </main>
</body></html>
"""


def test_collapsed_list_splits_into_per_section_sections():
    sections = DomCleaner().extract_sections(NESTED, {"content_area": "#content"})
    headings = [s.heading for s in sections]
    # one section per numbered provision, not one giant blob
    assert "1  Short title" in headings
    assert "2A  Objects of this Act" in headings
    assert "6  Interpretation" in headings
    assert len(sections) >= 4


def test_part_label_becomes_parent_path_without_duplicated_body():
    sections = DomCleaner().extract_sections(NESTED, {"content_area": "#content"})
    by_heading = {s.heading: s for s in sections}
    short_title = by_heading["1  Short title"]
    # Act title is the root, Part is the parent
    assert short_title.path[0] == "Privacy Act 1988 No. 119, 1988"
    assert "Part I-Preliminary" in short_title.path
    # the aggregate's duplicated body must NOT leak into a section's text
    assert "Commencement" not in short_title.text


def test_section_6_is_under_part_two():
    sections = DomCleaner().extract_sections(NESTED, {"content_area": "#content"})
    s6 = {s.heading: s for s in sections}["6  Interpretation"]
    assert "Part II-Interpretation" in s6.path


def test_generic_heading_page_is_unchanged():
    """Guard: pages without numbered-list collapse keep the old h1-h4 behaviour."""
    html = """
    <main>
      <h2>Part IV</h2>
      <p>General rules.</p>
      <h3 id="s26">Section 26</h3>
      <p>An organisation shall not transfer personal data overseas.</p>
    </main>
    """
    sections = DomCleaner().extract_sections(html, {"content_area": "main"})
    assert sections[1].path == ("Part IV", "Section 26")
    assert sections[1].anchor == "s26"

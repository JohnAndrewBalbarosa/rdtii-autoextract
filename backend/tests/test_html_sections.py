from core.domain.document import HtmlSection
from adapters.botting.l6_presentation.html_sections import (
    format_location_ref,
    join_section_text,
    section_for_offset,
)


def test_join_section_text_uses_shared_separator():
    sections = (
        HtmlSection("Section 1", "First body."),
        HtmlSection("Section 2", "Second body."),
    )

    assert join_section_text(sections) == "Section 1\nFirst body.\n\nSection 2\nSecond body."


def test_section_for_offset_maps_flattened_text_back_to_section():
    sections = (
        HtmlSection("Section 1", "No transfer here."),
        HtmlSection("Section 26", "An organisation shall not transfer personal data overseas."),
    )
    text = join_section_text(sections)

    section = section_for_offset(sections, text.index("overseas"))

    assert section == sections[1]


def test_section_for_offset_returns_none_for_invalid_offsets():
    sections = (HtmlSection("Section 1", "Body."),)

    assert section_for_offset(sections, -1) is None
    assert section_for_offset(sections, len(join_section_text(sections))) is None


def test_format_location_ref_prefers_anchor_then_path():
    anchored = HtmlSection("Section 26", "Body.", anchor="s26", path=("Part IV", "Section 26"))
    breadcrumb = HtmlSection("Section 26", "Body.", path=("Part IV", "Section 26"))

    assert format_location_ref(anchored) == "#s26"
    assert format_location_ref(anchored, base_url="https://example.gov/law") == "https://example.gov/law#s26"
    assert format_location_ref(breadcrumb) == "Part IV > Section 26"
    assert format_location_ref(None) == ""

"""Pure helpers for flattened HTML law sections and location references."""

from __future__ import annotations

from core.domain.document import HtmlSection

SECTION_SEPARATOR = "\n\n"


def _section_text(section: HtmlSection) -> str:
    parts = [part.strip() for part in (section.heading, section.text) if part and part.strip()]
    return "\n".join(parts)


def join_section_text(sections: list[HtmlSection] | tuple[HtmlSection, ...]) -> str:
    """Flatten sections using one separator shared with offset mapping."""
    return SECTION_SEPARATOR.join(
        text for section in sections if (text := _section_text(section))
    )


def section_for_offset(
    sections: list[HtmlSection] | tuple[HtmlSection, ...],
    offset: int,
) -> HtmlSection | None:
    """Return the section containing ``offset`` in ``join_section_text(sections)``."""
    if offset < 0:
        return None

    cursor = 0
    first = True
    for section in sections:
        text = _section_text(section)
        if not text:
            continue
        if not first:
            cursor += len(SECTION_SEPARATOR)
        end = cursor + len(text)
        if cursor <= offset < end:
            return section
        cursor = end
        first = False
    return None


def format_location_ref(section: HtmlSection | None, base_url: str | None = None) -> str:
    """Format a template-friendly HTML location reference."""
    if section is None:
        return ""
    if section.anchor:
        anchor = section.anchor.lstrip("#")
        return f"{base_url}#{anchor}" if base_url else f"#{anchor}"
    if section.path:
        return " > ".join(section.path)
    return ""

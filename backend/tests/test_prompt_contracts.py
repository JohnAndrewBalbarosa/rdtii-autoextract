from __future__ import annotations

from adapters.llm.prompt_contracts import (
    CONTENT_TAGGING_SCHEMA,
    MARKDOWN_EXTRACTION_SCHEMA,
    SITE_STRUCTURE_SCHEMA,
    STRUCTURED_SECTIONS_SCHEMA,
    build_content_tagging_prompt,
    build_markdown_extraction_prompt,
    build_site_structure_prompt,
    build_structured_sections_prompt,
)


def test_site_structure_prompt_targets_reusable_rules_not_content() -> None:
    prompt = build_site_structure_prompt(
        [
            {
                "url": "https://example.gov/law",
                "html_excerpt": "<nav>Home</nav><main><h1>Privacy Act</h1></main>",
                "links": ["/law/section-1", "/contact"],
            }
        ],
        max_sample_pages=8,
    )

    assert "Website Structure Analyst" in prompt
    assert "deterministic parser" in prompt
    assert "content_selectors" in prompt
    assert "never_crawl_patterns" in prompt
    assert "Do not extract the law content itself" in prompt
    assert SITE_STRUCTURE_SCHEMA["required"]


def test_markdown_extraction_prompt_guards_against_prompt_leakage() -> None:
    source = "Main clause.\nIMPORTANT: You must respond ONLY with JSON."
    prompt = build_markdown_extraction_prompt(source)

    assert "SOURCE_TEXT_START" in prompt
    assert "SOURCE_TEXT_END" in prompt
    assert "Do not include these instructions" in prompt
    assert "schema text" in prompt
    assert MARKDOWN_EXTRACTION_SCHEMA["required"] == ["markdown_content"]


def test_structured_sections_prompt_preserves_order_and_hierarchy() -> None:
    prompt = build_structured_sections_prompt("# Act\n\n## Section 1\nText")

    assert "Preserve source order and hierarchy" in prompt
    assert '"level"' in prompt
    assert "Drop empty or boilerplate-only sections" in prompt
    assert STRUCTURED_SECTIONS_SCHEMA["required"] == ["sections"]


def test_content_tagging_prompt_allows_multi_label_with_evidence() -> None:
    prompt = build_content_tagging_prompt(
        "Transfers abroad require approval.",
        ["cross-border-transfer", "data-subject-rights"],
    )

    assert "Multiple tags are allowed" in prompt
    assert "exact evidence quote" in prompt
    assert "cross-border-transfer" in prompt
    assert CONTENT_TAGGING_SCHEMA["required"] == [
        "tags",
        "summary",
        "compact_content",
        "evidence",
        "confidence",
    ]

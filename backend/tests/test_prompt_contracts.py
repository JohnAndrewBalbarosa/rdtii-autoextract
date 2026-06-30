from __future__ import annotations

from adapters.llm.prompt_contracts import (
    CONTENT_TAGGING_SCHEMA,
    LAYOUT_RULE_SCHEMA,
    LINK_DISCOVERY_SCHEMA,
    MARKDOWN_EXTRACTION_SCHEMA,
    SITE_STRUCTURE_SCHEMA,
    STRUCTURED_SECTIONS_SCHEMA,
    build_content_tagging_prompt,
    build_layout_rule_prompt,
    build_link_discovery_prompt,
    build_markdown_extraction_prompt,
    build_site_structure_prompt,
    build_structured_sections_prompt,
)


def test_link_discovery_prompt_samples_main_navigation_adaptively() -> None:
    prompt = build_link_discovery_prompt(
        "https://example.gov/",
        [{"url": "https://example.gov/laws", "text": "Laws"}],
    )
    assert "top navigation" in prompt
    assert "Do not select every" in prompt
    assert LINK_DISCOVERY_SCHEMA["required"] == ["selected_urls", "reason"]


def test_layout_prompt_defines_four_operational_roles_and_revision_evidence() -> None:
    prompt = build_layout_rule_prompt(
        [{"url": "https://example.gov/law", "html_excerpt": "<main>Law</main>"}],
        previous_rules={"rules": []},
        failures=[{"metric": "content_chars", "actual": 0}],
    )
    for role in ("ignore", "crawl_only", "extract_and_crawl", "extract_only"):
        assert role in prompt
    assert "VALIDATION_FAILURES" in prompt
    assert LAYOUT_RULE_SCHEMA["required"]


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

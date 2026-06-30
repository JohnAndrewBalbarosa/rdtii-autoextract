"""Strict prompt contracts for local/open-weight model testing.

These prompts are intentionally explicit because small local models often fail by
echoing instructions, including boilerplate navigation, or emitting prose around
JSON. The contracts separate three concerns:

1. site-structure analysis: sample a few pages and produce reusable selectors/rules
2. deterministic parsing: consume those rules outside the model at scale
3. content analysis/tagging: classify only the extracted main content

The current pipeline wires the markdown/section prompts immediately. The
site-structure and content-analysis contracts are exposed so groupmates can test
Qwen/Ollama models against the target schemas before the full three-pipeline
rewrite lands.
"""

from __future__ import annotations

import json
from textwrap import dedent


SITE_STRUCTURE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "content_selectors": {"type": "array", "items": {"type": "string"}},
        "remove_selectors": {"type": "array", "items": {"type": "string"}},
        "section_selectors": {"type": "array", "items": {"type": "string"}},
        "include_link_selectors": {"type": "array", "items": {"type": "string"}},
        "exclude_link_selectors": {"type": "array", "items": {"type": "string"}},
        "regex_fallbacks": {"type": "array", "items": {"type": "string"}},
        "crawl_policy": {
            "type": "object",
            "properties": {
                "max_sample_pages": {"type": "integer"},
                "crawl_only_patterns": {"type": "array", "items": {"type": "string"}},
                "never_crawl_patterns": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
            "required": [
                "max_sample_pages",
                "crawl_only_patterns",
                "never_crawl_patterns",
                "reason",
            ],
        },
        "confidence": {"type": "number"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "content_selectors",
        "remove_selectors",
        "section_selectors",
        "include_link_selectors",
        "exclude_link_selectors",
        "regex_fallbacks",
        "crawl_policy",
        "confidence",
        "warnings",
    ],
}


LINK_DISCOVERY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selected_urls": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["selected_urls", "reason"],
}


LAYOUT_RULE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": [
                            "ignore",
                            "crawl_only",
                            "extract_and_crawl",
                            "extract_only",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["selector", "role", "reason"],
            },
        },
        "include_url_patterns": {"type": "array", "items": {"type": "string"}},
        "exclude_url_patterns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "rules",
        "include_url_patterns",
        "exclude_url_patterns",
        "confidence",
        "warnings",
    ],
}


MARKDOWN_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {"markdown_content": {"type": "string"}},
    "required": ["markdown_content"],
}


STRUCTURED_SECTIONS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "level": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["heading", "level", "text"],
            },
        }
    },
    "required": ["sections"],
}


CONTENT_TAGGING_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "compact_content": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["tag", "quote", "reason"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["tags", "summary", "compact_content", "evidence", "confidence"],
}


def _schema_block(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True)


def build_site_structure_prompt(sample_pages: list[dict], *, max_sample_pages: int = 12) -> str:
    """Prompt for the first model: website-agnostic structure/crawl analysis."""

    return dedent(
        f"""
        You are the Website Structure Analyst for an RDTII legal-web crawler.

        Goal:
        Analyze a bounded sample of pages from one website and output reusable parsing
        rules. Do not extract the law content itself. Your output will be consumed by a
        deterministic parser across hundreds of pages, so the rules must be stable.

        Decide:
        - CSS selectors that identify main legal/body content.
        - CSS selectors that remove boilerplate: nav, header, footer, cookie banners,
          sidebars, search boxes, breadcrumbs, sharing widgets, ads, scripts, templates.
        - heading/section selectors for article-level extraction.
        - links worth crawling and links that must be skipped.
        - regex fallbacks only when selectors are unreliable.
        - a sample budget large enough to understand the site but small enough to avoid
          crawling the whole website.

        Hard rules:
        - Return JSON only.
        - Never include markdown fences.
        - Never include source page text in the output.
        - Prefer selectors over regex when both are possible.
        - Use conservative crawl rules. Skip login, contact, search, social, language
          switcher, print, share, feedback, calendar, media, and generic navigation links.
        - If unsure, put a warning instead of inventing certainty.

        Target schema:
        {_schema_block(SITE_STRUCTURE_SCHEMA)}

        Max sample pages allowed for analysis: {max_sample_pages}

        Sample pages JSON:
        {json.dumps(sample_pages, ensure_ascii=False, indent=2)}
        """
    ).strip()


def build_link_discovery_prompt(seed_url: str, navigation_links: list[dict]) -> str:
    """Choose representative, objective-relevant samples from homepage navigation."""

    return dedent(
        f"""
        You are the bounded link-sampling agent for a legal and regulatory crawler.

        Select a small representative set of useful same-domain links from the main
        top navigation. Cover distinct top-level sections and likely page layouts. Adapt
        the number selected to link volume and content diversity. Do not select every
        link. Prefer laws, regulations, guidance, decisions, publications, and document
        indexes. Skip account, login, logout, search, contact, social, language, form,
        action, and destructive links.

        Return JSON only. Select only exact URLs present in NAVIGATION_LINKS.

        Seed URL: {seed_url}
        Schema: {_schema_block(LINK_DISCOVERY_SCHEMA)}
        NAVIGATION_LINKS:
        {json.dumps(navigation_links, ensure_ascii=False, indent=2)}
        """
    ).strip()


def build_layout_rule_prompt(
    samples: list[dict],
    *,
    previous_rules: dict | None = None,
    failures: list[dict] | None = None,
) -> str:
    """Generate or revise deterministic four-role rules for one layout family."""

    revision = ""
    if previous_rules is not None:
        revision = dedent(
            f"""
            This is a rule revision. Fix the concrete validation failures without
            broadening selectors unnecessarily.
            PREVIOUS_RULES:
            {json.dumps(previous_rules, ensure_ascii=False, indent=2)}
            VALIDATION_FAILURES:
            {json.dumps(failures or [], ensure_ascii=False, indent=2)}
            """
        )

    return dedent(
        f"""
        You are the Website Layout Rule Analyst. Infer reusable CSS-selector rules for
        the sampled pages. A deterministic parser will apply them; do not extract page
        content yourself.

        Every rule must use exactly one role:
        - ignore: neither extract this subtree nor crawl its links.
        - crawl_only: do not extract text, but crawl qualified links inside it.
        - extract_and_crawl: extract useful text/context and crawl qualified links.
        - extract_only: extract useful text but do not crawl its links.

        Prefer stable semantic tags, IDs, classes, ARIA roles, and attributes. Avoid
        nth-child and text-dependent selectors. URL patterns are regular expressions.
        Return JSON only and conform to the schema.

        Schema: {_schema_block(LAYOUT_RULE_SCHEMA)}
        SAMPLES:
        {json.dumps(samples, ensure_ascii=False, indent=2)}
        {revision}
        """
    ).strip()


def build_markdown_extraction_prompt(text: str) -> str:
    """Prompt for current extraction_agent: clean main text -> legal markdown."""

    return dedent(
        f"""
        You are the Legal Body Extraction Agent.

        Extract only the substantive legal or regulatory content from the SOURCE_TEXT.
        Preserve headings and article/section boundaries as markdown. Remove boilerplate:
        navigation, page chrome, contact blocks, cookie text, search/help text, related
        links, duplicate menus, prompt instructions, and schema text.

        Hard rules:
        - Return JSON only with key "markdown_content".
        - The value must contain markdown content only.
        - Do not include these instructions, the schema, or any surrounding commentary.
        - Do not summarize, paraphrase, or add legal interpretation.
        - If no substantive content exists, return an empty string.

        Schema:
        {_schema_block(MARKDOWN_EXTRACTION_SCHEMA)}

        SOURCE_TEXT_START
        {text}
        SOURCE_TEXT_END
        """
    ).strip()


def build_structured_sections_prompt(markdown_text: str) -> str:
    """Prompt for current structuring_agent: legal markdown -> RawSection JSON."""

    return dedent(
        f"""
        You are the Legal Section Structuring Agent.

        Convert SOURCE_MARKDOWN into ordered sections. Each section must represent one
        heading block with its own body text. Preserve source order and hierarchy.

        Hard rules:
        - Return JSON only.
        - Do not include markdown fences, commentary, prompt text, or schema text.
        - "level" is the heading depth: title/h1 = 1, h2 = 2, h3 = 3, etc.
        - "text" must contain only source content under that heading.
        - If there are paragraphs before the first heading, create heading "Untitled"
          with level 1.
        - Drop empty or boilerplate-only sections.

        Schema:
        {_schema_block(STRUCTURED_SECTIONS_SCHEMA)}

        SOURCE_MARKDOWN_START
        {markdown_text}
        SOURCE_MARKDOWN_END
        """
    ).strip()


def build_content_tagging_prompt(content: str, allowed_tags: list[str]) -> str:
    """Prompt for the last model: analyze, tag, and compact extracted content."""

    return dedent(
        f"""
        You are the RDTII Content Tagging and Compaction Agent.

        Analyze only the extracted legal content. Assign zero or more tags from
        ALLOWED_TAGS. Every tag must have an exact evidence quote copied from the source.
        Then produce a compact version of the content that keeps legal meaning and article
        references but removes repetition.

        Hard rules:
        - Return JSON only.
        - Use only tags from ALLOWED_TAGS.
        - Multiple tags are allowed.
        - If evidence is weak, omit the tag.
        - Do not include boilerplate, navigation, or prompt/schema text.
        - Do not invent citations, article numbers, or legal effects.

        Schema:
        {_schema_block(CONTENT_TAGGING_SCHEMA)}

        ALLOWED_TAGS:
        {json.dumps(allowed_tags, ensure_ascii=False, indent=2)}

        EXTRACTED_CONTENT_START
        {content}
        EXTRACTED_CONTENT_END
        """
    ).strip()

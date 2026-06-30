"""Bounded AI-assisted domain crawler with deterministic parsing and validation."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.robotparser
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from bs4 import BeautifulSoup

from adapters.botting.l4_transport.pdf_parser import PdfParser
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.llm.prompt_contracts import (
    LAYOUT_RULE_SCHEMA,
    LINK_DISCOVERY_SCHEMA,
    build_layout_rule_prompt,
    build_link_discovery_prompt,
)
from core.ports import HtmlFetcherPort, LLMProvider


_BLOCKED_URL_PARTS = re.compile(
    r"(?:^|[/_.?=&-])(login|logout|signin|signout|delete|remove|action|account|register|captcha)(?:$|[/_.?=&-])",
    re.IGNORECASE,
)
_BOILERPLATE = ("cookie", "all rights reserved", "skip to content", "privacy policy")
_ROLES = {"ignore", "crawl_only", "extract_and_crawl", "extract_only"}


@dataclass(frozen=True)
class CrawlConfig:
    max_depth: int = 2
    max_pages: int = 30
    max_revision_attempts: int = 2
    min_content_chars: int = 80
    user_agent: str = "ZetarixResearchCrawler/1.0"


class RobotsPolicy:
    """Cached robots.txt policy; replaceable in tests."""

    def __init__(self) -> None:
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, url: str, user_agent: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._parsers:
            parser = urllib.robotparser.RobotFileParser(urllib.parse.urljoin(origin, "/robots.txt"))
            try:
                parser.read()
            except Exception:
                # Network failure is not permission. Fail closed for live crawling.
                return False
            self._parsers[origin] = parser
        return self._parsers[origin].can_fetch(user_agent, url)


class AdaptiveDomainCrawler:
    """Observe, learn, validate, revise, then crawl one domain in memory."""

    def __init__(
        self,
        fetcher: HtmlFetcherPort,
        llm: LLMProvider,
        *,
        cleaner: Optional[DomCleaner] = None,
        scaffold_registry: Optional[ScaffoldRegistry] = None,
        pdf_parser: Optional[PdfParser] = None,
        robots_allowed: Optional[Callable[[str, str], bool]] = None,
        config: Optional[CrawlConfig] = None,
    ) -> None:
        self._fetcher = fetcher
        self._llm = llm
        self._cleaner = cleaner or DomCleaner()
        self._scaffolds = scaffold_registry or ScaffoldRegistry()
        self._pdf_parser = pdf_parser or PdfParser()
        self._robots = robots_allowed or RobotsPolicy().allowed
        self._config = config or CrawlConfig()
        self._layouts: dict[str, dict] = {}

    def crawl(self, seed_url: str) -> dict:
        seed = self._canonicalize(seed_url)
        if not seed or urllib.parse.urlsplit(seed).scheme not in {"http", "https"}:
            raise ValueError("seed_url must be an absolute HTTP(S) URL")
        seed_host = self._host(seed)
        result = {
            "visited_urls": [],
            "skipped_urls": [],
            "failed_urls": [],
            "extracted_pages": [],
            "learned_layouts": [],
        }

        if not self._robots(seed, self._config.user_agent):
            result["skipped_urls"].append({"url": seed, "reason": "robots_disallowed"})
            return result

        try:
            seed_html, seed_is_pdf = self._fetch(seed)
        except Exception as exc:
            result["failed_urls"].append({"url": seed, "reason": f"fetch_error: {exc}"})
            return result
        if seed_is_pdf:
            result["failed_urls"].append({"url": seed, "reason": "seed_page_is_pdf"})
            return result

        nav_links = self._navigation_links(seed_html, seed, seed_host)
        discovery = self._llm.complete(
            build_link_discovery_prompt(seed, nav_links),
            LINK_DISCOVERY_SCHEMA,
            agent_profile="link_discovery_agent",
        )
        selected = self._sanitize_selected(discovery.get("selected_urls", []), nav_links, seed_host)

        queue = deque([(seed, 0), *((url, 1) for url in selected)])
        queued = {seed, *selected}
        visited: set[str] = set()
        # The homepage was already fetched for navigation observation. Reuse it so a
        # crawl never double-hits the seed merely because discovery is a separate stage.
        prefetched = {seed: (seed_html, False)}

        while queue and len(visited) < self._config.max_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            rejection = self._url_rejection(url, seed_host, depth)
            if rejection:
                result["skipped_urls"].append({"url": url, "reason": rejection})
                continue
            if not self._robots(url, self._config.user_agent):
                result["skipped_urls"].append({"url": url, "reason": "robots_disallowed"})
                continue

            try:
                payload, is_pdf = prefetched.pop(url) if url in prefetched else self._fetch(url)
                visited.add(url)
                result["visited_urls"].append(url)
                if is_pdf:
                    text = self._pdf_parser.extract_text(payload)
                    result["extracted_pages"].append(self._page_result(url, "pdf", "pdf_parser", text, [], 0))
                    continue

                layout_id, fingerprint = self._layout_fingerprint(payload)
                layout = self._layouts.get(layout_id)
                if layout is None:
                    layout = self._learn_layout(layout_id, fingerprint, url, payload)
                    self._layouts[layout_id] = layout

                parsed = self._apply_rules(payload, url, layout["rules"], seed_host)
                method = "ai_rules"
                failures = self._validation_failures(parsed)
                while failures and layout["revision_count"] < self._config.max_revision_attempts:
                    revised = self._llm.complete(
                        build_layout_rule_prompt(
                            [self._sample(url, payload)],
                            previous_rules=layout["rules"],
                            failures=failures,
                        ),
                        LAYOUT_RULE_SCHEMA,
                        agent_profile="rule_revision_agent",
                    )
                    layout["rules"] = self._normalize_rules(revised)
                    layout["revision_count"] += 1
                    parsed = self._apply_rules(payload, url, layout["rules"], seed_host)
                    failures = self._validation_failures(parsed)

                if failures:
                    text = self._cleaner.clean_html(payload)
                    method = "readability"
                    if len(text.strip()) < self._config.min_content_chars:
                        scaffold = self._scaffolds.get_scaffold_for_url(url)
                        if scaffold is None:
                            result["failed_urls"].append({"url": url, "reason": "no_domain_specific_fallback"})
                            continue
                        text = self._cleaner.clean_html(payload, scaffold.get_custom_selectors())
                        method = "domain_scaffold"
                    if len(text.strip()) < self._config.min_content_chars:
                        result["failed_urls"].append({"url": url, "reason": "all_extraction_methods_failed"})
                        continue
                    parsed = {"text": text, "links": []}

                layout["sample_urls"].append(url) if url not in layout["sample_urls"] else None
                layout["validation"] = {"passed": not failures, "failures": failures}
                layout["final_extraction_method"] = method
                result["extracted_pages"].append(
                    self._page_result(url, layout_id, method, parsed["text"], parsed["links"], layout["revision_count"])
                )
                if depth < self._config.max_depth:
                    for link in parsed["links"]:
                        if link not in queued and len(queued) < self._config.max_pages * 4:
                            queued.add(link)
                            queue.append((link, depth + 1))
            except Exception as exc:
                visited.add(url)
                result["failed_urls"].append({"url": url, "reason": f"processing_error: {exc}"})

        for url, _depth in queue:
            result["skipped_urls"].append({"url": url, "reason": "max_pages_reached"})
        result["learned_layouts"] = list(self._layouts.values())
        return result

    @staticmethod
    def write_json(result: dict, path) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)

    def _fetch(self, url: str):
        if hasattr(self._fetcher, "fetch_raw"):
            response = self._fetcher.fetch_raw(url)
            return (response.body if response.is_pdf else response.text), response.is_pdf
        return self._fetcher.fetch(url), url.lower().endswith(".pdf")

    def _learn_layout(self, layout_id: str, fingerprint: dict, url: str, html: str) -> dict:
        response = self._llm.complete(
            build_layout_rule_prompt([self._sample(url, html)]),
            LAYOUT_RULE_SCHEMA,
            agent_profile="layout_rule_agent",
        )
        return {
            "layout_id": layout_id,
            "fingerprint": fingerprint,
            "sample_urls": [url],
            "rules": self._normalize_rules(response),
            "validation": {"passed": False, "failures": []},
            "revision_count": 0,
            "final_extraction_method": "ai_rules",
        }

    def _apply_rules(self, html: str, base_url: str, rule_set: dict, seed_host: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        rules = rule_set.get("rules", [])
        for rule in rules:
            if rule["role"] == "ignore":
                for node in list(soup.select(rule["selector"])):
                    node.decompose()

        texts: list[str] = []
        links: list[str] = []
        for rule in rules:
            role = rule["role"]
            if role == "ignore":
                continue
            for node in soup.select(rule["selector"]):
                if role in {"extract_only", "extract_and_crawl"}:
                    text = node.get_text(" ", strip=True)
                    if text and text not in texts:
                        texts.append(text)
                if role in {"crawl_only", "extract_and_crawl"}:
                    candidates = [node] if getattr(node, "name", None) == "a" else node.select("a[href]")
                    for anchor in candidates:
                        link = self._canonicalize(urllib.parse.urljoin(base_url, anchor.get("href", "")))
                        if link and not self._url_rejection(link, seed_host, 0) and self._matches_url_rules(link, rule_set):
                            if link not in links:
                                links.append(link)
        return {"text": "\n".join(texts), "links": links}

    def _validation_failures(self, parsed: dict) -> list[dict]:
        text = parsed["text"].strip()
        failures = []
        if len(text) < self._config.min_content_chars:
            failures.append({"metric": "content_chars", "actual": len(text), "minimum": self._config.min_content_chars})
        lowered = text.lower()
        contamination = [term for term in _BOILERPLATE if term in lowered]
        if contamination:
            failures.append({"metric": "boilerplate", "terms": contamination})
        return failures

    def _navigation_links(self, html: str, base_url: str, seed_host: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        containers = soup.select("header nav, nav, [role=navigation]")
        anchors = [a for node in containers for a in node.select("a[href]")]
        if not anchors:
            anchors = soup.select("body a[href]")[:100]
        output = []
        seen = set()
        for anchor in anchors:
            url = self._canonicalize(urllib.parse.urljoin(base_url, anchor.get("href", "")))
            if url and url not in seen and not self._url_rejection(url, seed_host, 1):
                seen.add(url)
                output.append({"url": url, "text": anchor.get_text(" ", strip=True)[:160]})
        return output

    def _sanitize_selected(self, selected: list, available: list[dict], seed_host: str) -> list[str]:
        allowed = {item["url"] for item in available}
        output = []
        for raw in selected:
            url = self._canonicalize(str(raw))
            if url in allowed and not self._url_rejection(url, seed_host, 1) and url not in output:
                output.append(url)
        return output

    def _layout_fingerprint(self, html: str) -> tuple[str, dict]:
        soup = BeautifulSoup(html, "html.parser")
        fingerprint = {
            "landmarks": sorted({tag.name for tag in soup.select("header, nav, main, article, aside, footer")}),
            "heading_levels": sorted({tag.name for tag in soup.select("h1, h2, h3, h4, h5, h6")}),
            "body_classes": sorted((soup.body.get("class", []) if soup.body else []))[:8],
            "main_signatures": sorted(
                {f"{tag.name}#{tag.get('id', '')}.{'.'.join(tag.get('class', [])[:3])}" for tag in soup.select("main, article, [role=main]")}
            )[:8],
        }
        digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:12]
        return f"layout-{digest}", fingerprint

    @staticmethod
    def _sample(url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("script, style, template, noscript"):
            tag.decompose()
        compact = str(soup)[:30000]
        return {"url": url, "html_excerpt": compact}

    @staticmethod
    def _normalize_rules(response: dict) -> dict:
        rules = []
        for item in response.get("rules", []):
            selector = str(item.get("selector", "")).strip()
            role = item.get("role")
            if selector and role in _ROLES:
                rules.append({"selector": selector, "role": role, "reason": str(item.get("reason", ""))})
        return {
            "rules": rules,
            "include_url_patterns": list(response.get("include_url_patterns", [])),
            "exclude_url_patterns": list(response.get("exclude_url_patterns", [])),
            "confidence": response.get("confidence", 0),
            "warnings": list(response.get("warnings", [])),
        }

    @staticmethod
    def _matches_url_rules(url: str, rules: dict) -> bool:
        try:
            if any(re.search(pattern, url) for pattern in rules.get("exclude_url_patterns", [])):
                return False
            include = rules.get("include_url_patterns", [])
            return not include or any(re.search(pattern, url) for pattern in include)
        except re.error:
            return False

    @staticmethod
    def _canonicalize(url: str) -> str:
        try:
            parsed = urllib.parse.urlsplit(url.strip())
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                return ""
            host = parsed.hostname.lower() if parsed.hostname else ""
            port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
            path = re.sub(r"/{2,}", "/", parsed.path or "/")
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
            return urllib.parse.urlunsplit((parsed.scheme.lower(), host + port, path.rstrip("/") or "/", urllib.parse.urlencode(sorted(query)), ""))
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _host(url: str) -> str:
        host = urllib.parse.urlsplit(url).hostname or ""
        return host.lower().removeprefix("www.")

    def _url_rejection(self, url: str, seed_host: str, depth: int) -> str:
        if self._host(url) != seed_host:
            return "different_domain"
        if depth > self._config.max_depth:
            return "max_depth_exceeded"
        if _BLOCKED_URL_PARTS.search(url):
            return "unsafe_or_account_url"
        return ""

    @staticmethod
    def _page_result(url: str, layout_id: str, method: str, text: str, links: list[str], revisions: int) -> dict:
        return {
            "source_url": url,
            "canonical_url": url,
            "layout_id": layout_id,
            "extraction_method": method,
            "content": text,
            "discovered_links": links,
            "rule_version": revisions + 1,
            "warnings": [],
        }

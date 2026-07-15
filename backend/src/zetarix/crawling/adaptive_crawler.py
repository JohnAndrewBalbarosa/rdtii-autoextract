"""Bounded AI-assisted domain crawler with deterministic parsing and validation."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.robotparser
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from bs4 import BeautifulSoup

from zetarix.cleaning.dom_cleaner import DomCleaner
from zetarix.extraction.document_metadata import extract_document_metadata
from zetarix.llm.prompt_contracts import (
    LAYOUT_RULE_SCHEMA,
    LINK_DISCOVERY_SCHEMA,
    LINK_RELEVANCE_SCHEMA,
    build_layout_rule_prompt,
    build_link_discovery_prompt,
    build_link_relevance_prompt,
)
from zetarix.ports import HtmlFetcherPort, LLMProvider
from zetarix.scaffolds.scaffold_registry import ScaffoldRegistry
from zetarix.transport.fetch_result import FetchResult
from zetarix.transport.pdf_parser import PdfParser

_BLOCKED_URL_PARTS = re.compile(
    r"(?:^|[/_.?=&-])(login|logout|signin|signout|delete|remove|action|account|register|captcha)(?:$|[/_.?=&-])",
    re.IGNORECASE,
)
_NOISE_URL_PARTS = re.compile(
    r"(?:^|[/_.?=&-])(careers|career|jobs|news|media|events|calendar|press|contact|about|feedback|faq|subscribe|search|privacy|terms|copyright|facebook|twitter|linkedin|youtube|instagram)(?:$|[/_.?=&-])",
    re.IGNORECASE,
)
_HARD_NOISE_URL_PARTS = re.compile(
    r"(?:^|[/_.?=&-])("
    r"contact(?:-us)?|privacy-statement|terms(?:-and-conditions)?|news|announcements?|"
    r"media-release|press-release|feedback|faq|copyright"
    r")(?:$|[/_.?=&-])",
    re.IGNORECASE,
)
_BOILERPLATE = ("cookie", "all rights reserved", "skip to content", "privacy policy")
_NON_LEGAL_PAGE_TITLES = re.compile(
    r"\b(contact us|privacy statement|terms and conditions|overview|news|announcement|media release)\b",
    re.IGNORECASE,
)
_ROLES = {"ignore", "crawl_only", "extract_and_crawl", "extract_only"}
_DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".zip")
_DISCOVERY_KEYWORDS = (
    "law",
    "laws",
    "regulation",
    "regulations",
    "legislation",
    "legislative",
    "act",
    "bill",
    "gazette",
    "policy",
    "policies",
    "directive",
    "directives",
    "order",
    "orders",
    "circular",
    "guidance",
    "guidelines",
    "privacy",
    "personal data",
    "data protection",
    "cross-border",
    "digital trade",
    "e-commerce",
    "cyber",
    "ict",
    "ministry",
)
_VOLATILE_CLASS = re.compile(
    r"^(?:"
    r"is-[\w-]*|has-[\w-]*|js-[\w-]*|"
    r"active|selected|current|open|opened|closed|hidden|"
    r"show|shown|hide|focus|focused|hover|disabled|loading|expanded|collapsed|"
    r"(?:page|item|p|n|col|row|step|slide|tab)-?\d+|"
    r"[0-9a-f]{8,}|"
    r"\d+"
    r")$",
    re.IGNORECASE,
)


class ExtractionError(Exception):
    """One page could not be extracted by any method; carries a machine reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CrawlConfig:
    max_depth: int = 2
    max_pages: int = 30
    max_revision_attempts: int = 2
    min_content_chars: int = 80
    user_agent: str = "ZetarixResearchCrawler/1.0"
    crawl_objective: str = (
        "laws, regulations, guidance, decisions, publications, and official "
        "legal/regulatory documents"
    )


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
            "seed_url": seed,
            "crawl_started_at": self._now_iso(),
            "visited_urls": [],
            "skipped_urls": [],
            "failed_urls": [],
            "successful_fetches": [],
            "failed_fetches": [],
            "extracted_pages": [],
            "discovered_sources": [],
            "learned_layouts": [],
        }
        source_index: dict[str, dict[str, Any]] = {}

        if not self._robots(seed, self._config.user_agent):
            result["skipped_urls"].append({"url": seed, "reason": "robots_disallowed"})
            result["summary"] = self._summary(result, source_index)
            return result

        try:
            seed_payload, seed_is_pdf, seed_response = self._fetch(seed)
        except Exception as exc:
            result["failed_urls"].append({"url": seed, "reason": f"fetch_error: {exc}"})
            result["failed_fetches"].append(self._failed_fetch(seed, f"fetch_error: {exc}", found_on_url=None, crawl_depth=0))
            result["summary"] = self._summary(result, source_index)
            return result

        if seed_is_pdf:
            result["failed_urls"].append({"url": seed, "reason": "seed_page_is_pdf"})
            result["failed_fetches"].append(self._failed_fetch(seed, "seed_page_is_pdf", found_on_url=None, crawl_depth=0))
            result["summary"] = self._summary(result, source_index)
            return result

        nav_links = self._navigation_links(seed_payload, seed, seed_host)
        selected = self._discover_seed_links(seed, nav_links, seed_host)

        queue = deque([(seed, 0, None), *((url, 1, seed) for url in selected)])
        queued = {seed, *selected}
        visited: set[str] = set()
        prefetched = {seed: (seed_payload, False, seed_response)}

        self._record_source(source_index, url=seed, source_page=None, crawl_depth=0, status="queued", document_type="html")
        for url in selected:
            self._record_source(
                source_index,
                url=url,
                source_page=seed,
                crawl_depth=1,
                status="queued",
                document_type=self._document_type_for_url(url),
            )

        while queue and len(visited) < self._config.max_pages:
            url, depth, found_on_url = queue.popleft()
            if url in visited:
                self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="duplicate", dedupe_status="duplicate")
                continue

            rejection = self._url_rejection(url, seed_host, depth)
            if rejection:
                result["skipped_urls"].append({"url": url, "reason": rejection})
                self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="skipped")
                continue
            if not self._robots(url, self._config.user_agent):
                result["skipped_urls"].append({"url": url, "reason": "robots_disallowed"})
                self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="skipped")
                continue

            try:
                payload, is_pdf, response = prefetched.pop(url) if url in prefetched else self._fetch(url)
                visited.add(url)
                result["visited_urls"].append(url)
                result["successful_fetches"].append(self._fetch_metadata(response, found_on_url=found_on_url, crawl_depth=depth))

                page = self.scrape_page(
                    url,
                    seed_host=seed_host,
                    payload=payload,
                    is_pdf=is_pdf,
                    depth=depth,
                    response=response,
                    found_on_url=found_on_url,
                )
                result["extracted_pages"].append(page)
                self._record_source(
                    source_index,
                    url=url,
                    source_page=found_on_url,
                    crawl_depth=depth,
                    status="fetched",
                    title=page.get("title", ""),
                    document_type=page.get("document_type", self._document_type_for_url(url)),
                    domain=page.get("domain", self._host(url)),
                    http_status=page.get("http_status"),
                    content_type=page.get("content_type", ""),
                    checksum=page.get("checksum"),
                    publication_date=page.get("publication_date"),
                    provenance=page.get("provenance"),
                )

                for candidate in page.get("link_candidates", []):
                    self._record_source(
                        source_index,
                        url=candidate["url"],
                        source_page=url,
                        crawl_depth=depth + 1,
                        title=candidate.get("name", ""),
                        document_type=self._document_type_for_url(candidate["url"]),
                        status="discovered",
                    )

                if depth < self._config.max_depth:
                    candidates = page.get("link_candidates") or [
                        {"url": link, "name": ""} for link in page["discovered_links"]
                    ]
                    for link in self._select_useful_links(candidates, self._config.crawl_objective):
                        if link not in queued and len(queued) < self._config.max_pages * 4:
                            queued.add(link)
                            queue.append((link, depth + 1, url))
            except ExtractionError as exc:
                result["failed_urls"].append({"url": url, "reason": exc.reason})
                result["failed_fetches"].append(self._failed_fetch(url, exc.reason, found_on_url=found_on_url, crawl_depth=depth))
                self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="failed")
            except Exception as exc:
                visited.add(url)
                result["failed_urls"].append({"url": url, "reason": f"processing_error: {exc}"})
                result["failed_fetches"].append(self._failed_fetch(url, f"processing_error: {exc}", found_on_url=found_on_url, crawl_depth=depth))
                self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="failed")

        for url, depth, found_on_url in queue:
            result["skipped_urls"].append({"url": url, "reason": "max_pages_reached"})
            self._record_source(source_index, url=url, source_page=found_on_url, crawl_depth=depth, status="queued")

        result["learned_layouts"] = list(self._layouts.values())
        result["discovered_sources"] = list(source_index.values())
        result["summary"] = self._summary(result, source_index)
        return result

    def scrape_page(
        self,
        url: str,
        *,
        seed_host: Optional[str] = None,
        payload: Optional[str] = None,
        is_pdf: Optional[bool] = None,
        depth: int = 0,
        response: Optional[FetchResult] = None,
        found_on_url: Optional[str] = None,
    ) -> dict:
        seed_host = seed_host or self._host(url)
        if payload is None:
            payload, is_pdf, response = self._fetch(url)
        if response is None:
            response = self._fetch_response(url)

        if is_pdf:
            text = self._pdf_parser.extract_text(payload)
            return self._page_result(
                url,
                "pdf",
                "pdf_parser",
                text,
                [],
                0,
                depth=depth,
                response=response,
                found_on_url=found_on_url,
            )

        layout_id, fingerprint = self._layout_fingerprint(payload)
        layout = self._layouts.get(layout_id)
        if layout is None:
            layout = self._learn_layout(layout_id, fingerprint, url, payload)
            self._layouts[layout_id] = layout

        parsed = self._apply_rules(payload, url, layout["rules"], seed_host)
        method = "ai_rules"
        failures = self._validation_failures(parsed)
        while failures and layout["revision_count"] < self._config.max_revision_attempts:
            try:
                revised = self._llm.complete(
                    build_layout_rule_prompt(
                        [self._sample(url, payload)],
                        previous_rules=layout["rules"],
                        failures=failures,
                    ),
                    LAYOUT_RULE_SCHEMA,
                    agent_profile="rule_revision_agent",
                )
            except Exception:
                revised = self._heuristic_rule_set(url)
            layout["rules"] = self._normalize_rules(revised)
            layout["revision_count"] += 1
            parsed = self._apply_rules(payload, url, layout["rules"], seed_host)
            failures = self._validation_failures(parsed)

        if failures:
            text = self._cleaner.clean_html(payload)
            method = "readability"
            scaffold = self._scaffolds.get_scaffold_for_url(url)
            selectors = scaffold.get_custom_selectors() if scaffold else {}
            links, named_links = self._heuristic_links(payload, url, seed_host, selectors)
            if len(text.strip()) < self._config.min_content_chars:
                if scaffold is None:
                    raise ExtractionError("no_domain_specific_fallback")
                text = self._cleaner.clean_html(payload, selectors)
                method = "domain_scaffold"
            if len(text.strip()) < self._config.min_content_chars:
                raise ExtractionError("all_extraction_methods_failed")
            parsed = {"text": text, "links": links, "named_links": named_links}

        if url not in layout["sample_urls"]:
            layout["sample_urls"].append(url)
        layout["validation"] = {"passed": not failures, "failures": failures}
        layout["final_extraction_method"] = method
        page = self._page_result(
            url,
            layout_id,
            method,
            parsed["text"],
            parsed["links"],
            layout["revision_count"],
            depth=depth,
            response=response,
            found_on_url=found_on_url,
        )
        page["link_candidates"] = parsed.get("named_links", [])
        return page

    @staticmethod
    def write_json(result: dict, path) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)

    def _fetch_response(self, url: str) -> FetchResult:
        if hasattr(self._fetcher, "fetch_raw"):
            return self._fetcher.fetch_raw(url)
        content = self._fetcher.fetch(url)
        if isinstance(content, bytes):
            body = content
        else:
            body = content.encode("utf-8", errors="replace")
        content_type = "application/pdf" if self._document_type_for_url(url) == "pdf" else "text/html; charset=utf-8"
        return FetchResult(url=url, status=200, content_type=content_type, body=body)

    def _fetch(self, url: str):
        response = self._fetch_response(url)
        return (response.body if response.is_pdf else response.text), response.is_pdf, response

    def _learn_layout(self, layout_id: str, fingerprint: dict, url: str, html: str) -> dict:
        try:
            response = self._llm.complete(
                build_layout_rule_prompt([self._sample(url, html)]),
                LAYOUT_RULE_SCHEMA,
                agent_profile="layout_rule_agent",
            )
        except Exception:
            response = self._heuristic_rule_set(url)
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
        named_links: list[dict] = []
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
                        if not link:
                            continue
                        if self._url_rejection(link, seed_host, 0):
                            continue
                        if not self._matches_url_rules(link, rule_set):
                            continue
                        if link not in links:
                            links.append(link)
                            named_links.append({"url": link, "name": anchor.get_text(" ", strip=True)[:160]})
        for item in self._embedded_document_links(html, base_url, seed_host):
            if item["url"] not in links:
                links.append(item["url"])
                named_links.append(item)
        return {"text": "\n".join(texts), "links": links, "named_links": named_links}

    def _embedded_document_links(self, html: str, base_url: str, seed_host: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        named_links: list[dict] = []
        seen: set[str] = set()

        def add(url: str, name: str) -> None:
            canonical = self._canonicalize(urllib.parse.urljoin(base_url, url))
            if not canonical or canonical in seen or self._url_rejection(canonical, seed_host, 0):
                return
            seen.add(canonical)
            named_links.append({"url": canonical, "name": name[:160]})

        for tag_name, attr in (
            ("iframe", "src"),
            ("frame", "src"),
            ("embed", "src"),
            ("object", "data"),
            ("source", "src"),
        ):
            for node in soup.select(f"{tag_name}[{attr}]"):
                raw = node.get(attr, "")
                name = node.get("title", "") or node.get("aria-label", "") or tag_name
                add(raw, name)

        for match in re.findall(r'https?://[^\s"\'<>]+', html, re.IGNORECASE):
            if any(fragment in match.lower() for fragment in ("/text/", ".pdf", ".doc", ".epub", "document_")):
                add(match, "")

        return named_links

    def _select_useful_links(self, candidates: list[dict], objective: str) -> list[str]:
        if not candidates:
            return []
        allowed = {item["url"] for item in candidates}
        fallback = [item["url"] for item in candidates]
        try:
            response = self._llm.complete(
                build_link_relevance_prompt(candidates, objective),
                LINK_RELEVANCE_SCHEMA,
                agent_profile="link_relevance_agent",
            )
        except Exception:
            return fallback
        if not isinstance(response, dict) or "selected_urls" not in response:
            return fallback
        chosen = {url for url in response.get("selected_urls", []) if url in allowed}
        ranked = [item["url"] for item in candidates if item["url"] in chosen]
        return ranked or fallback

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

    def _discover_seed_links(self, seed: str, nav_links: list[dict], seed_host: str) -> list[str]:
        heuristic = self._heuristic_link_selection(nav_links, self._config.crawl_objective, limit=12)
        try:
            discovery = self._llm.complete(
                build_link_discovery_prompt(seed, nav_links),
                LINK_DISCOVERY_SCHEMA,
                agent_profile="link_discovery_agent",
            )
        except Exception:
            return heuristic
        if not isinstance(discovery, dict):
            return heuristic
        selected = self._sanitize_selected(discovery.get("selected_urls", []), nav_links, seed_host)
        return selected or heuristic

    def _heuristic_links(
        self,
        html: str,
        base_url: str,
        seed_host: str,
        selectors: Optional[dict[str, str]] = None,
    ) -> tuple[list[str], list[dict]]:
        soup = BeautifulSoup(html, "html.parser")
        selected_nodes: list[Any] = []
        if selectors:
            for key in ("article_links", "pdf_links"):
                selector = selectors.get(key)
                if selector:
                    selected_nodes.extend(soup.select(selector))
        if not selected_nodes:
            container = soup.find("main") or soup.find("article") or soup.find("body") or soup
            selected_nodes = container.select("a[href]")

        named_links: list[dict] = []
        seen: set[str] = set()
        for anchor in selected_nodes:
            href = anchor.get("href", "")
            url = self._canonicalize(urllib.parse.urljoin(base_url, href))
            if not url or url in seen or self._url_rejection(url, seed_host, 0):
                continue
            seen.add(url)
            named_links.append({"url": url, "name": anchor.get_text(" ", strip=True)[:160]})

        for match in re.findall(r'https?://[^\s"\'<>]+', html, re.IGNORECASE):
            url = self._canonicalize(match)
            if not url or url in seen or self._url_rejection(url, seed_host, 0):
                continue
            if self._document_type_for_url(url) == "html":
                continue
            seen.add(url)
            named_links.append({"url": url, "name": ""})

        return [item["url"] for item in named_links], named_links

    def _heuristic_link_selection(
        self,
        candidates: list[dict],
        objective: str,
        *,
        limit: Optional[int] = None,
    ) -> list[str]:
        ranked: list[tuple[int, int, str]] = []
        for i, item in enumerate(candidates):
            url = item.get("url", "")
            name = item.get("name") or item.get("text") or ""
            score = self._link_score(url, name, objective)
            if score > 0:
                ranked.append((score, -i, url))
        ranked.sort(reverse=True)
        urls = [url for _score, _i, url in ranked]
        if limit is not None:
            urls = urls[:limit]
        if urls:
            return urls
        documents = [item["url"] for item in candidates if self._document_type_for_url(item.get("url", "")) != "html"]
        return documents or [item["url"] for item in candidates[: min(len(candidates), limit or len(candidates))]]

    def _link_score(self, url: str, name: str, objective: str) -> int:
        text = f"{name} {url} {objective}".lower()
        score = 0
        if self._document_type_for_url(url) != "html":
            score += 6
        if _HARD_NOISE_URL_PARTS.search(url):
            score -= 12
        if _NOISE_URL_PARTS.search(url):
            score -= 5
        if _BLOCKED_URL_PARTS.search(url):
            score -= 8
        for keyword in _DISCOVERY_KEYWORDS:
            if keyword in text:
                score += 2
        if any(fragment in text for fragment in ("download", "attachment", "document", "gazette", "statute")):
            score += 2
        if any(fragment in text for fragment in ("news", "event", "speech", "media release", "career", "contact us")):
            score -= 4
        return score

    def _heuristic_rule_set(self, url: str) -> dict:
        scaffold = self._scaffolds.get_scaffold_for_url(url)
        content_selector = "main, article, #content, .content, .page-content, body"
        if scaffold:
            selectors = scaffold.get_custom_selectors()
            content_selector = selectors.get("content_area", content_selector)
        return {
            "rules": [
                {"selector": "header, footer, nav, script, style, template, noscript", "role": "ignore", "reason": "boilerplate"},
                {"selector": content_selector, "role": "extract_and_crawl", "reason": "main content area"},
            ],
            "include_url_patterns": [r"\.(pdf|docx?|xlsx?|pptx?|rtf)$", r"(law|regulation|act|policy|gazette|guidance|directive|circular|order|privacy|data|digital|trade|ict|e-?commerce)"],
            "exclude_url_patterns": [r"(login|logout|contact|careers|social|terms)"],
            "confidence": 0.4,
            "warnings": ["heuristic layout fallback used"],
        }

    @staticmethod
    def _stable_classes(soup: BeautifulSoup) -> list[str]:
        classes: set[str] = set()
        for element in soup.find_all(True):
            for token in element.get("class") or []:
                token = token.strip().lower()
                if token and not _VOLATILE_CLASS.match(token):
                    classes.add(token)
        return sorted(classes)

    def _layout_fingerprint(self, html: str) -> tuple[str, dict]:
        soup = BeautifulSoup(html, "html.parser")
        fingerprint = {
            "landmarks": sorted({tag.name for tag in soup.select("header, nav, main, article, aside, footer")}),
            "heading_levels": sorted({tag.name for tag in soup.select("h1, h2, h3, h4, h5, h6")}),
            "stable_classes": self._stable_classes(soup),
        }
        digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:12]
        return f"layout-{digest}", fingerprint

    @staticmethod
    def _sample(url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("script, style, template, noscript"):
            tag.decompose()
        for text_node in soup.find_all(string=True):
            text_node.replace_with("")
        return {"url": url, "html_excerpt": str(soup)[:30000]}

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
            query_str = urllib.parse.urlencode(sorted(query))
            return urllib.parse.urlunsplit((parsed.scheme.lower(), host + port, path.rstrip("/") or "/", query_str, ""))
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
        if _HARD_NOISE_URL_PARTS.search(url):
            return "non_legal_noise_url"
        if _BLOCKED_URL_PARTS.search(url):
            return "unsafe_or_account_url"
        return ""

    def _page_result(
        self,
        url: str,
        layout_id: str,
        method: str,
        text: str,
        links: list[str],
        revisions: int,
        *,
        depth: int,
        response: FetchResult,
        found_on_url: Optional[str],
    ) -> dict:
        title, publication_date = self._document_metadata(text=text, response=response)
        warnings: list[str] = []
        if _NON_LEGAL_PAGE_TITLES.search(title) or _HARD_NOISE_URL_PARTS.search(url):
            warnings.append("non_legal_page")
        return {
            "source_url": url,
            "canonical_url": url,
            "layout_id": layout_id,
            "extraction_method": method,
            "content": text,
            "discovered_links": links,
            "rule_version": revisions + 1,
            "warnings": warnings,
            "title": title,
            "document_type": self._document_type_for_response(response),
            "domain": self._host(url),
            "crawl_timestamp": self._now_iso(),
            "crawl_depth": depth,
            "http_status": response.status,
            "content_type": response.content_type,
            "checksum": hashlib.sha256(response.body).hexdigest()[:16],
            "publication_date": publication_date,
            "found_on_url": found_on_url,
            "provenance": {"found_on_url": found_on_url, "crawl_depth": depth},
        }

    def _document_metadata(self, *, text: str, response: FetchResult) -> tuple[str, str | None]:
        if response.is_pdf:
            metadata = extract_document_metadata(text, url=response.url)
            return metadata.act_title[:300], metadata.last_update.isoformat() if metadata.last_update else None

        soup = BeautifulSoup(response.text, "html.parser")
        title = ""
        for attrs in (
            {"property": "og:title"},
            {"name": "dcterms.title"},
            {"name": "dc.title"},
            {"name": "twitter:title"},
        ):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                title = meta["content"].strip()
                break
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(" ", strip=True) if h1 else ""
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            title = extract_document_metadata(text, url=response.url).act_title

        publication_date = None
        for selector in (
            ("meta", {"property": "article:published_time"}),
            ("meta", {"name": "publishdate"}),
            ("meta", {"name": "publication_date"}),
            ("meta", {"name": "dcterms.date"}),
            ("meta", {"name": "date"}),
            ("time", {}),
        ):
            node = soup.find(selector[0], attrs=selector[1])
            if node is None:
                continue
            if selector[0] == "meta":
                value = node.get("content", "").strip()
            else:
                value = node.get("datetime", "").strip() or node.get_text(" ", strip=True)
            if value:
                publication_date = value[:64]
                break
        return title[:300], publication_date

    def _document_type_for_response(self, response: FetchResult) -> str:
        return "pdf" if response.is_pdf else self._document_type_for_url(response.url)

    def _document_type_for_url(self, url: str) -> str:
        path = urllib.parse.urlsplit(url).path.lower()
        for ext in _DOC_EXTENSIONS:
            if path.endswith(ext):
                return ext.lstrip(".")
        return "html"

    def _fetch_metadata(self, response: FetchResult, *, found_on_url: Optional[str], crawl_depth: int) -> dict[str, Any]:
        return {
            "url": response.url,
            "normalized_url": self._canonicalize(response.url),
            "http_status": response.status,
            "content_type": response.content_type,
            "document_type": self._document_type_for_response(response),
            "checksum": hashlib.sha256(response.body).hexdigest()[:16],
            "crawl_timestamp": self._now_iso(),
            "crawl_depth": crawl_depth,
            "found_on_url": found_on_url,
        }

    def _failed_fetch(self, url: str, reason: str, *, found_on_url: Optional[str], crawl_depth: int) -> dict[str, Any]:
        return {
            "url": url,
            "normalized_url": self._canonicalize(url),
            "reason": reason,
            "crawl_timestamp": self._now_iso(),
            "crawl_depth": crawl_depth,
            "found_on_url": found_on_url,
        }

    def _record_source(
        self,
        source_index: dict[str, dict[str, Any]],
        *,
        url: str,
        source_page: Optional[str],
        crawl_depth: int,
        status: str,
        title: str = "",
        document_type: str = "html",
        domain: Optional[str] = None,
        http_status: Optional[int] = None,
        content_type: str = "",
        checksum: Optional[str] = None,
        publication_date: Optional[str] = None,
        provenance: Optional[dict[str, Any]] = None,
        dedupe_status: str = "unique",
    ) -> None:
        normalized = self._canonicalize(url)
        if not normalized:
            return
        item = source_index.get(normalized)
        if item is None:
            item = {
                "url": url,
                "normalized_url": normalized,
                "title": title,
                "document_type": document_type,
                "country": self._country_for_url(url),
                "domain": domain or self._host(url),
                "crawl_timestamp": self._now_iso(),
                "http_status": http_status,
                "content_type": content_type,
                "checksum": checksum,
                "publication_date": publication_date,
                "source_pages": [],
                "crawl_depth": crawl_depth,
                "status": status,
                "dedupe_status": dedupe_status,
                "provenance": provenance or {},
            }
            source_index[normalized] = item
        else:
            item["dedupe_status"] = "duplicate" if status == "duplicate" else item.get("dedupe_status", dedupe_status)
            if status in {"fetched", "failed"}:
                item["status"] = status
            if title and not item.get("title"):
                item["title"] = title
            if http_status is not None:
                item["http_status"] = http_status
            if content_type:
                item["content_type"] = content_type
            if checksum:
                item["checksum"] = checksum
            if publication_date and not item.get("publication_date"):
                item["publication_date"] = publication_date
            item["crawl_depth"] = min(item.get("crawl_depth", crawl_depth), crawl_depth)
            if provenance:
                item["provenance"] = provenance
        if source_page and source_page not in item["source_pages"]:
            item["source_pages"].append(source_page)

    def _country_for_url(self, url: str) -> str:
        host = self._host(url)
        if host.endswith(".gov.sg") or "sso.agc.gov.sg" in host or "pdpc.gov.sg" in host:
            return "Singapore"
        if host.endswith(".gov.au"):
            return "Australia"
        if host.endswith(".gov.my"):
            return "Malaysia"
        return ""

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _summary(result: dict, source_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return {
            "visited_count": len(result.get("visited_urls", [])),
            "skipped_count": len(result.get("skipped_urls", [])),
            "failed_count": len(result.get("failed_urls", [])),
            "fetched_count": len(result.get("successful_fetches", [])),
            "failed_fetch_count": len(result.get("failed_fetches", [])),
            "discovered_source_count": len(source_index),
            "document_source_count": sum(1 for item in source_index.values() if item.get("document_type") != "html"),
            "duplicate_source_count": sum(1 for item in source_index.values() if item.get("dedupe_status") == "duplicate"),
        }

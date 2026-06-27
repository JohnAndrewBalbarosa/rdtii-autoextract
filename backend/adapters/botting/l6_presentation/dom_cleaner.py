import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from core.domain.document import HtmlSection

# UI-chrome heuristics: drop SHORT blocks that are clearly SPA navigation/widgets, while
# keeping any block with substantial text (real statute text never looks like these).
_NAV_STOPWORDS = {
    "text", "details", "authorises", "downloads", "all versions", "interactions",
    "menu", "search", "home", "login", "sign in", "contact us", "share",
    "skip to content", "breadcrumb", "navigation", "print", "feedback", "citation change",
}
_CHROME_ANCHOR_RE = re.compile(
    r"(tab|dropdown|accordion|carousel|modal|cookie|breadcrumb|navbar|menu|skip|toolbar)",
    re.IGNORECASE,
)
_MIN_CONTENT_CHARS_FOR_CHROME = 200  # below this a nav-looking block is treated as chrome

# Bug #2 fix: collapsed list-of-provisions pages (e.g. legislation.gov.au) carry provisions
# as <li> with a section-number prefix, wrapped by "Collapse Part/Division …" aggregate <li>
# that duplicate child text. These let us split one giant section into per-provision sections.
_SECTION_NUM_RE = re.compile(r"^\d+[A-Z]*\s+\S")  # "1  Short title", "2A  Objects"
_STRUCT_RE = re.compile(r"^(?:Collapse\s+)?(Part|Division|Subdivision|Chapter)\b", re.I)
_KIND_ORDER = {"chapter": 0, "part": 1, "division": 2, "subdivision": 3}
_ACT_TITLE_RE = re.compile(
    r"\b(Act|Regulations?|Code|Ordinance|Decree|Law)\b.*\b(19|20)\d{2}\b", re.I
)


class DomCleaner:
    """OSI Layer 6 (Presentation): Translates raw HTML bytes/strings into clean, readable text."""

    def clean_html(self, html_content: str, selectors: dict | None = None) -> str:
        """Strips boilerplate and returns clean text."""
        soup = BeautifulSoup(html_content, "html.parser")
        self._strip_boilerplate(soup, selectors.get("boilerplate") if selectors else None)
        
        # If content_area selector is provided, try to find it
        main_content = None
        if selectors and "content_area" in selectors:
            main_content = self._select_first_by_priority(soup, selectors["content_area"])
        
        if not main_content:
            main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup

        texts = []
        
        # Use custom sections selector if available, else default to standard tags
        if selectors and "sections" in selectors:
            elements = main_content.select(selectors["sections"])
        else:
            elements = main_content.find_all(['h1', 'h2', 'h3', 'p', 'li'])
        
        for element in elements:
            texts.append(element.get_text(strip=True))
            
        return "\n".join(texts)

    def extract_sections(self, html_content: str, selectors: dict | None = None) -> list[HtmlSection]:
        """Extract legal-content sections with anchors and heading breadcrumbs."""
        soup = BeautifulSoup(html_content, "html.parser")
        self._strip_boilerplate(soup, selectors.get("boilerplate") if selectors else None)
        main_content = self._content_area(soup, selectors)

        elements = self._collect_block_elements(main_content, selectors)
        groups = self._group_elements(elements)
        act_title = self._detect_act_title(soup)
        split_groups: list[dict] = []
        for group in groups:
            split_groups.extend(self._split_numbered_list_group(group, act_title))
        return [
            HtmlSection(
                heading=group["heading"],
                text=group["text"],
                anchor=group["anchor"],
                path=group["path"],
            )
            for group in split_groups
            if self._group_is_kept(group)
        ]

    def annotate_html(self, html_content: str, selectors: dict | None = None) -> str:
        """Mark — instead of remove — the elements the AI reads, for the dev inspector.

        Single source of truth: this reuses the exact collection/grouping/chrome logic of
        ``extract_sections`` so the headful inspector shows precisely what the headless
        production path keeps. Survivors get ``data-zx-keep="1"`` (plus ``data-zx-anchor`` /
        ``data-zx-path`` when known); discards get ``data-zx-drop="<reason>"``.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        boiler_ids: set[int] = set()
        extra = selectors.get("boilerplate") if selectors else None
        for selector in self._boilerplate_selectors(extra):
            try:
                matches = list(soup.select(selector))
            except Exception:
                continue
            for element in matches:
                element["data-zx-drop"] = "boilerplate"
                boiler_ids.add(id(element))
                for descendant in element.find_all(True):
                    boiler_ids.add(id(descendant))

        main_content = self._content_area(soup, selectors)
        elements = [
            element
            for element in self._collect_block_elements(main_content, selectors)
            if id(element) not in boiler_ids
        ]

        for group in self._group_elements(elements):
            kept = self._group_is_kept(group)
            path_label = " › ".join(group["path"]) if group["path"] else ""
            for member in group["members"]:
                if kept:
                    member["data-zx-keep"] = "1"
                    anchor = self._nearest_anchor(member)
                    if anchor:
                        member["data-zx-anchor"] = anchor
                    if path_label:
                        member["data-zx-path"] = path_label
                else:
                    member["data-zx-drop"] = "chrome"

        # Standard block tags the grouping never reached (outside the content area) are
        # content the AI ignores — mark them so the inspector can dim them with a reason.
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            if id(element) in boiler_ids:
                continue
            if element.get("data-zx-keep") or element.get("data-zx-drop"):
                continue
            element["data-zx-drop"] = "outside-content"

        return str(soup)

    def annotate_blocks(self, html_content: str, selectors: dict | None = None) -> dict:
        """Machine-readable keep/drop decision trace for the dev inspector (JSON).

        Reuses the EXACT collection/grouping/chrome logic of ``annotate_html`` /
        ``extract_sections`` (same private helpers) so the trace matches what the headless
        production path keeps. Returns a dict::

            {"summary": {...}, "blocks": [ {tag, anchor, path, decision, reason,
                                            char_count, preview, selector_hit?}, ... ]}

        ``decision`` is ``"kept"`` or ``"skipped"``; ``reason`` is ``kept`` | ``chrome`` |
        ``boilerplate`` | ``outside-content``. ``selector_hit`` (boilerplate only) names the
        selector that dropped the block. ``summary.potential_false_skips`` counts SKIPPED
        blocks that still hold substantial text (>= the chrome threshold) — the blocks a
        reviewer must check, because real law/article text could be hiding in a sidebar/nav
        the selector logic ignored.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Map every boilerplate element (and descendants) to the selector that matched it.
        boiler_hit: dict[int, str] = {}
        extra = selectors.get("boilerplate") if selectors else None
        for selector in self._boilerplate_selectors(extra):
            try:
                matches = list(soup.select(selector))
            except Exception:
                continue
            for element in matches:
                boiler_hit.setdefault(id(element), selector)
                for descendant in element.find_all(True):
                    boiler_hit.setdefault(id(descendant), selector)

        main_content = self._content_area(soup, selectors)
        elements = [
            element
            for element in self._collect_block_elements(main_content, selectors)
            if id(element) not in boiler_hit
        ]

        blocks: list[dict] = []
        seen_ids: set[int] = set()
        for group in self._group_elements(elements):
            kept = self._group_is_kept(group)
            path = list(group["path"])
            for member in group["members"]:
                text = member.get_text(" ", strip=True)
                if not text:
                    continue
                seen_ids.add(id(member))
                blocks.append(
                    self._block_record(
                        member,
                        text,
                        "kept" if kept else "skipped",
                        "kept" if kept else "chrome",
                        path=path,
                    )
                )

        # Standard text blocks the content grouping never reached: either boilerplate
        # (dropped by a selector) or outside the content area. These are where real text
        # can hide, so surface them too.
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            if id(element) in seen_ids:
                continue
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            if id(element) in boiler_hit:
                blocks.append(
                    self._block_record(
                        element, text, "skipped", "boilerplate", selector_hit=boiler_hit[id(element)]
                    )
                )
            else:
                blocks.append(self._block_record(element, text, "skipped", "outside-content"))

        return {"summary": self._trace_summary(blocks), "blocks": blocks}

    def _block_record(
        self,
        element,
        text: str,
        decision: str,
        reason: str,
        *,
        path: list[str] | None = None,
        selector_hit: str | None = None,
    ) -> dict:
        record = {
            "tag": (element.name or "").lower(),
            "anchor": self._nearest_anchor(element),
            "path": path or [],
            "decision": decision,
            "reason": reason,
            "char_count": len(text),
            "preview": text[:160],
        }
        if selector_hit:
            record["selector_hit"] = selector_hit
        return record

    def _trace_summary(self, blocks: list[dict]) -> dict:
        dropped: dict[str, int] = {}
        kept = 0
        chars_kept = 0
        false_skips = 0
        for block in blocks:
            if block["decision"] == "kept":
                kept += 1
                chars_kept += block["char_count"]
            else:
                dropped[block["reason"]] = dropped.get(block["reason"], 0) + 1
                if block["char_count"] >= _MIN_CONTENT_CHARS_FOR_CHROME:
                    false_skips += 1
        return {
            "kept": kept,
            "chars_kept": chars_kept,
            "dropped": dropped,
            "potential_false_skips": false_skips,
        }

    def discover_links(self, html_content: str, selectors: dict[str, str]) -> dict[str, list[str]]:
        """Extracts PDF and internal article links based on the provided selectors."""
        soup = BeautifulSoup(html_content, "html.parser")
        results = {
            "pdf_links": [],
            "article_links": []
        }
        
        if not selectors:
            return results

        if "pdf_links" in selectors:
            for link in soup.select(selectors["pdf_links"]):
                href = link.get("href")
                if href:
                    results["pdf_links"].append(href)

        if "article_links" in selectors:
            for link in soup.select(selectors["article_links"]):
                href = link.get("href")
                if href:
                    results["article_links"].append(href)
                    
        # Remove duplicates
        results["pdf_links"] = list(set(results["pdf_links"]))
        results["article_links"] = list(set(results["article_links"]))
        
        return results

    def _content_area(self, soup, selectors: dict | None):
        if selectors and "content_area" in selectors:
            main_content = self._select_first_by_priority(soup, selectors["content_area"])
            if main_content:
                return main_content
        return soup.find("main") or soup.find("article") or soup.find("body") or soup

    def _select_first_by_priority(self, soup, selector_list: str):
        for selector in selector_list.split(","):
            selector = selector.strip()
            if not selector:
                continue
            try:
                match = soup.select_one(selector)
            except Exception:
                continue
            if match is not None:
                return match
        return None

    def _boilerplate_selectors(self, extra_selectors: str | list[str] | None = None) -> list[str]:
        """The single boilerplate selector list shared by stripping and annotating."""
        selectors = [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "aside",
            "form",
            "[role='navigation']",
            "[role='search']",
            "[role='banner']",
            "[role='contentinfo']",
        ]
        if isinstance(extra_selectors, str):
            selectors.append(extra_selectors)
        elif extra_selectors:
            selectors.extend(extra_selectors)
        return selectors

    def _strip_boilerplate(self, soup, extra_selectors=None) -> None:
        for selector in self._boilerplate_selectors(extra_selectors):
            try:
                matches = list(soup.select(selector))
            except Exception:
                continue
            for element in matches:
                element.decompose()

    def _nearest_anchor(self, element) -> str | None:
        anchor = element.get("id") if hasattr(element, "get") else None
        if anchor:
            return str(anchor)
        child_with_anchor = element.find(id=True) if hasattr(element, "find") else None
        if child_with_anchor is not None:
            return str(child_with_anchor.get("id"))
        cursor = element
        while cursor is not None:
            anchor = cursor.get("id") if hasattr(cursor, "get") else None
            if anchor:
                return str(anchor)
            cursor = cursor.parent
        return None

    def _has_nested_standard_block(self, element) -> bool:
        return element.find(["h1", "h2", "h3", "h4", "p", "li"]) is not None

    def _collect_block_elements(self, main_content: Tag, selectors: dict | None) -> list[Tag]:
        """Ordered legal-content block elements: standard tags plus custom-selected leaves."""
        selected_ids: set[int] = set()
        if selectors and selectors.get("sections"):
            try:
                selected_ids = {id(element) for element in main_content.select(selectors["sections"])}
            except Exception:
                selected_ids = set()

        block_tags = {"h1", "h2", "h3", "h4", "p", "li"}
        elements = []
        for element in main_content.find_all(True):
            name = (element.name or "").lower()
            is_standard_block = name in block_tags
            is_custom_block = id(element) in selected_ids and not self._has_nested_standard_block(element)
            if is_standard_block or is_custom_block:
                elements.append(element)
        return elements

    def _group_elements(self, elements: list[Tag]) -> list[dict]:
        """Group ordered block elements into heading-scoped sections, tracking source members."""
        groups: list[dict] = []
        heading_stack: list[tuple[int, str]] = []
        current: dict | None = None

        def start_group(heading: str, anchor: str | None, path: tuple[str, ...]) -> dict:
            return {"heading": heading, "anchor": anchor, "path": path, "members": [], "_texts": []}

        for element in elements:
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            name = (element.name or "").lower()
            if name in {"h1", "h2", "h3", "h4"}:
                if current is not None:
                    groups.append(current)
                level = int(name[1])
                heading_stack = [(lvl, value) for lvl, value in heading_stack if lvl < level]
                heading_stack.append((level, text))
                current = start_group(
                    text,
                    self._nearest_anchor(element),
                    tuple(value for _, value in heading_stack),
                )
                current["members"].append(element)
            else:
                if current is None:
                    current = start_group("", self._nearest_anchor(element), ())
                current["_texts"].append(text)
                current["members"].append(element)

        if current is not None:
            groups.append(current)

        for group in groups:
            group["text"] = "\n".join(part for part in group.pop("_texts") if part)
        return groups

    def _detect_act_title(self, soup) -> str | None:
        """Find the law's title (e.g. 'Privacy Act 1988 No. 119, 1988') anywhere on the page.

        It usually sits in the masthead, OUTSIDE the content area, so it is otherwise dropped.
        The aligned design uses it as the root of every section's breadcrumb path.
        """
        for tag in soup.find_all(["h1", "h2", "title"]):
            text = tag.get_text(" ", strip=True)
            if text and _ACT_TITLE_RE.search(text):
                return text
        return None

    def _structural_label(self, text: str) -> str:
        """'Collapse Part I-Preliminary 1  Short title 2  …' -> 'Part I-Preliminary'."""
        label = re.sub(r"^Collapse\s+", "", text, flags=re.IGNORECASE).strip()
        cut = re.search(r"\s\d+[A-Z]*\s", label)
        if cut:
            label = label[: cut.start()]
        return label.strip()

    def _push_struct(self, stack: list[str], label: str) -> list[str]:
        """Maintain a Part>Division>Subdivision parent chain, replacing same/lower kinds."""
        kind = label.split()[0].lower() if label else ""
        level = _KIND_ORDER.get(kind)
        if level is None:
            return stack + [label]
        kept = [s for s in stack if _KIND_ORDER.get(s.split()[0].lower(), 99) < level]
        return kept + [label]

    def _split_numbered_list_group(self, group: dict, act_title: str | None = None) -> list[dict]:
        """Split a collapsed group into per-section sections when it holds a numbered list.

        Guarded: only triggers when the group has >= 2 leaf blocks whose text starts with a
        section-number prefix. Generic heading-structured pages are returned unchanged, so the
        existing h1-h4 behaviour (and its tests) is preserved. Part/Division aggregate <li>
        become parent breadcrumb labels (their duplicated body is dropped); the Act title is
        prepended as the path root.
        """
        members = group.get("members", [])

        def leaf_text(member) -> str:
            return member.get_text(" ", strip=True)

        starts = [
            member
            for member in members
            if not self._has_nested_standard_block(member) and _SECTION_NUM_RE.match(leaf_text(member))
        ]
        if len(starts) < 2:
            return [group]

        base_path = list(group.get("path", ()))
        if act_title and (not base_path or base_path[0] != act_title):
            base_path = [act_title] + base_path

        sections: list[dict] = []
        struct_stack: list[str] = []
        current: dict | None = None
        for member in members:
            text = leaf_text(member)
            if not text:
                continue
            is_section = not self._has_nested_standard_block(member) and bool(_SECTION_NUM_RE.match(text))
            if not is_section and _STRUCT_RE.match(text):
                struct_stack = self._push_struct(struct_stack, self._structural_label(text))
                continue
            if self._has_nested_standard_block(member):
                # Aggregate container without a structural label: drop its duplicated body.
                continue
            if is_section:
                path = tuple(part for part in base_path + struct_stack + [text] if part)
                current = {
                    "heading": text,
                    "anchor": self._nearest_anchor(member),
                    "path": path,
                    "members": [member],
                    "text": "",
                }
                sections.append(current)
            elif current is not None:
                current["text"] = (current["text"] + "\n" + text).strip()

        return sections or [group]

    def _group_is_kept(self, group: dict) -> bool:
        """A group reaches the AI iff it has content and is not short UI chrome."""
        if not (group["heading"] or group["text"]):
            return False
        return not self._is_ui_chrome(group["heading"], group["text"], group["anchor"])

    def _is_ui_chrome(self, heading: str, text: str, anchor: str | None) -> bool:
        """True for SHORT SPA nav/widget blocks (tabs, dropdowns, menus) — never real text.

        Length-gated: a block with substantial text is kept even if its anchor looks like a
        widget id (e.g. the legislation.gov.au text panel lives in an ``ngb-nav-*-panel``).
        """
        if len(text or "") >= _MIN_CONTENT_CHARS_FOR_CHROME:
            return False
        if (heading or "").strip().lower() in _NAV_STOPWORDS:
            return True
        if anchor and _CHROME_ANCHOR_RE.search(anchor):
            return True
        return False

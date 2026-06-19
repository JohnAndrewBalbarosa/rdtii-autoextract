"""FetchResult: typed binary-safe response wrapper for L4 transport."""
from __future__ import annotations

import re
from dataclasses import dataclass


def _is_text_content_type(content_type: str) -> bool:
    """Return True for MIME types that are text-decodable (HTML, plain text, XML, JSON)."""
    ct = content_type.lower().split(";")[0].strip()
    return ct.startswith("text/") or ct in (
        "application/json",
        "application/xml",
        "application/xhtml+xml",
    )


def _charset_from_content_type(content_type: str) -> str:
    """Extract charset from Content-Type header, defaulting to utf-8."""
    match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    return match.group(1).strip('"') if match else "utf-8"


@dataclass(frozen=True)
class FetchResult:
    """Immutable HTTP response; body is always raw bytes so binary PDFs never crash."""

    url: str
    status: int
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        """Decode body only for text-like content types; use errors='replace' as safety net."""
        if not _is_text_content_type(self.content_type):
            raise ValueError(
                f"Cannot decode non-text content-type '{self.content_type}' as text. "
                "Use .body for binary content."
            )
        charset = _charset_from_content_type(self.content_type)
        return self.body.decode(charset, errors="replace")

    @property
    def is_pdf(self) -> bool:
        ct = self.content_type.lower().split(";")[0].strip()
        return ct == "application/pdf" or self.url.lower().endswith(".pdf")

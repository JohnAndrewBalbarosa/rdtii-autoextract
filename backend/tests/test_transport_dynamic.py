"""Tests for TransportFactory SPA detection + forced-dynamic fetch."""

from __future__ import annotations

from adapters.botting.l4_transport.factory import TransportFactory
from adapters.botting.l4_transport.fetch_result import FetchResult


class _FakeRaw:
    def __init__(self, html: str) -> None:
        self._html = html

    def fetch_raw(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=self._html.encode("utf-8"),
        )


_SPA_SHELL = '<html><head><script src="main.js"></script></head><body><app-root ng-version="17.0"></app-root></body></html>'
_RENDERED = "<html><body><main><h1>Privacy Act 1988</h1><p>Section 6. " + ("text " * 400) + "</p></main></body></html>"
_RICH_STATIC = "<html><body><main><h1>Act</h1><p>" + ("real content " * 200) + "</p></main></body></html>"


def test_spa_shell_triggers_dynamic():
    factory = TransportFactory(_FakeRaw(_SPA_SHELL), _FakeRaw(_RENDERED))
    result = factory.fetch_raw("https://x.gov/spa")
    assert "Privacy Act 1988" in result.text  # dynamic engine output returned


def test_rich_static_not_overridden():
    factory = TransportFactory(_FakeRaw(_RICH_STATIC), _FakeRaw(_RENDERED))
    result = factory.fetch_raw("https://x.gov/page")
    assert "real content" in result.text  # static kept; dynamic not used


def test_fetch_raw_dynamic_forces_dynamic_engine():
    factory = TransportFactory(_FakeRaw(_RICH_STATIC), _FakeRaw(_RENDERED))
    result = factory.fetch_raw_dynamic("https://x.gov/page")
    assert "Privacy Act 1988" in result.text

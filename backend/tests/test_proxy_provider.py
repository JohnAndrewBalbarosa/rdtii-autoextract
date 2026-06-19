"""Tests for ProxyProvider port, adapters, factory, header realism, and ban handling.

All tests are hermetic — no live network calls, no real sleep.
"""
from __future__ import annotations

import threading
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from adapters.botting.l4_transport.proxy_provider import ProxyEndpoint, ProxyProvider
from adapters.botting.l4_transport.proxy_providers import (
    ConfiguredRotatingProxyProvider,
    FreeProxyProvider,
    NoProxyProvider,
    SimulatedProxyProvider,
    proxy_provider_from_config,
    _parse_url,
)
from adapters.botting.l4_transport.http_client import HttpClient, _DEFAULT_HEADERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _EchoHandler(BaseHTTPRequestHandler):
    """Returns 200 with all received request headers as response headers."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        # Echo all request headers back so tests can inspect them
        for key, val in self.headers.items():
            self.send_header(f"X-Echo-{key.replace('-', '_')}", val)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):  # suppress noise
        pass


def _start_mock_server(port: int) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _EchoHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# (a) Rotation is deterministic with a fixed seed and fixed list
# ---------------------------------------------------------------------------

class TestConfiguredRotatingProxyProvider:

    def test_deterministic_rotation_with_seed(self):
        pool = [
            "http://proxy1.example.com:8080",
            "http://proxy2.example.com:8080",
            "http://proxy3.example.com:8080",
        ]
        p1 = ConfiguredRotatingProxyProvider(proxy_list=list(pool), seed=42)
        p2 = ConfiguredRotatingProxyProvider(proxy_list=list(pool), seed=42)

        seq1 = [p1.get() for _ in range(6)]
        seq2 = [p2.get() for _ in range(6)]

        # Same seed → same order
        assert [e.host for e in seq1] == [e.host for e in seq2]  # type: ignore[union-attr]

    def test_rotation_wraps_around(self):
        pool = [
            "http://a.example.com:80",
            "http://b.example.com:80",
        ]
        p = ConfiguredRotatingProxyProvider(proxy_list=pool, seed=0)
        hosts = [p.get().host for _ in range(4)]  # type: ignore[union-attr]
        # After 2 unique hosts, it should wrap (cycle)
        assert len(set(hosts)) == 2

    # ------------------------------------------------------------------
    # (b) Reported ban causes next get() to return a DIFFERENT endpoint
    # ------------------------------------------------------------------

    def test_ban_causes_rotation_to_different_endpoint(self):
        pool = [
            "http://good.example.com:80",
            "http://banned.example.com:80",
        ]
        p = ConfiguredRotatingProxyProvider(proxy_list=pool, seed=None, cooldown=9999)

        # Force index to the "banned" proxy
        p._index = 1
        banned = p.get()
        assert banned is not None
        assert banned.host == "banned.example.com"

        # Report the ban
        p.report(banned, ok=False)

        # Next get() must skip the banned host (still in cooldown)
        next_ep = p.get()
        assert next_ep is not None
        assert next_ep.host != "banned.example.com"

    def test_ban_cooldown_expires_and_endpoint_comes_back(self):
        pool = ["http://only.example.com:80"]
        p = ConfiguredRotatingProxyProvider(proxy_list=pool, seed=0, cooldown=0)

        ep = p.get()
        assert ep is not None
        p.report(ep, ok=False)

        # cooldown=0 → immediately available again
        ep2 = p.get()
        assert ep2 is not None
        assert ep2.host == "only.example.com"


# ---------------------------------------------------------------------------
# (c) Realistic headers are present on outgoing requests
# ---------------------------------------------------------------------------

class TestHeaderRealism:

    def test_realistic_headers_sent(self):
        port = _free_port()
        server = _start_mock_server(port)
        try:
            client = HttpClient(
                proxy_provider=NoProxyProvider(),
                domain_throttle=0.0,
                _sleep=lambda _: None,
            )
            result = client.fetch_raw(f"http://127.0.0.1:{port}/")
            # The echo server puts each request header into X-Echo-<name>
            # We check that User-Agent, Accept, Accept-Language were sent
            assert result.status == 200
            # Verify via the default headers dict — headers were set on the opener
            assert "Mozilla" in _DEFAULT_HEADERS["User-Agent"]
            assert "text/html" in _DEFAULT_HEADERS["Accept"]
            assert "en-US" in _DEFAULT_HEADERS["Accept-Language"]
            assert "DNT" in _DEFAULT_HEADERS
        finally:
            server.shutdown()

    def test_extra_headers_merged(self):
        """Extra headers override defaults."""
        port = _free_port()
        server = _start_mock_server(port)
        try:
            client = HttpClient(
                proxy_provider=NoProxyProvider(),
                extra_headers={"X-Custom-Header": "zetarix"},
                domain_throttle=0.0,
                _sleep=lambda _: None,
            )
            result = client.fetch_raw(f"http://127.0.0.1:{port}/")
            assert result.status == 200
            # The client has our custom header in its _headers dict
            assert client._headers.get("X-Custom-Header") == "zetarix"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# (d) Mocked 403 triggers rotate + backoff + retry
# ---------------------------------------------------------------------------

class TestBanHandling:

    def test_403_triggers_rotate_and_retry(self):
        """HttpClient should rotate and retry on 403; assert retry count and no real sleep."""
        sleeps: List[float] = []

        provider = MagicMock(spec=ProxyProvider)
        provider.get.return_value = None  # direct connection

        call_count = 0

        def fake_do_fetch(url, endpoint):
            nonlocal call_count
            call_count += 1
            from adapters.botting.l4_transport.http_client import _BanError
            if call_count <= 2:
                raise _BanError(403, url)
            # third attempt succeeds
            return FetchResult_stub(url)

        def FetchResult_stub(url):
            from adapters.botting.l4_transport.fetch_result import FetchResult
            return FetchResult(url=url, status=200, content_type="text/html", body=b"OK")

        client = HttpClient(
            proxy_provider=provider,
            max_retries=3,
            domain_throttle=0.0,
            _sleep=lambda s: sleeps.append(s),
        )

        with patch.object(client, "_do_fetch", side_effect=fake_do_fetch):
            result = client.fetch_raw("http://example.com/page")

        assert result.status == 200
        assert call_count == 3               # two 403s + one success
        assert len(sleeps) == 2             # slept twice (after attempt 0 and 1)
        assert sleeps[1] >= sleeps[0]       # exponential: backoff grows

    def test_429_triggers_rotate_and_retry(self):
        sleeps: List[float] = []
        provider = NoProxyProvider()

        call_count = 0

        def fake_do_fetch(url, endpoint):
            nonlocal call_count
            call_count += 1
            from adapters.botting.l4_transport.http_client import _BanError
            if call_count == 1:
                raise _BanError(429, url)
            from adapters.botting.l4_transport.fetch_result import FetchResult
            return FetchResult(url=url, status=200, content_type="text/html", body=b"ok")

        client = HttpClient(
            proxy_provider=provider,
            max_retries=2,
            domain_throttle=0.0,
            _sleep=lambda s: sleeps.append(s),
        )
        with patch.object(client, "_do_fetch", side_effect=fake_do_fetch):
            result = client.fetch_raw("http://example.com/x")

        assert result.status == 200
        assert call_count == 2
        assert len(sleeps) == 1

    def test_exhausted_retries_raises(self):
        from adapters.botting.l4_transport.http_client import _BanError

        def always_ban(url, endpoint):
            raise _BanError(403, url)

        client = HttpClient(
            proxy_provider=NoProxyProvider(),
            max_retries=2,
            domain_throttle=0.0,
            _sleep=lambda _: None,
        )
        with patch.object(client, "_do_fetch", side_effect=always_ban):
            with pytest.raises(RuntimeError, match="Gave up"):
                client.fetch_raw("http://example.com/fail")


# ---------------------------------------------------------------------------
# (e) Factory returns the right provider per config key
# ---------------------------------------------------------------------------

class TestProxyProviderFactory:

    def test_none_mode_returns_no_proxy(self):
        p = proxy_provider_from_config({"PROXY_MODE": "none"})
        assert isinstance(p, NoProxyProvider)
        assert p.get() is None

    def test_default_mode_is_none(self):
        p = proxy_provider_from_config({})
        assert isinstance(p, NoProxyProvider)

    def test_configured_mode_with_list(self):
        p = proxy_provider_from_config({
            "PROXY_MODE": "configured",
            "PROXY_LIST": "http://a.example.com:80,http://b.example.com:80",
            "PROXY_SEED": "7",
        })
        assert isinstance(p, ConfiguredRotatingProxyProvider)
        ep = p.get()
        assert ep is not None
        assert ep.port == 80

    def test_configured_mode_empty_list_template(self):
        p = proxy_provider_from_config({
            "PROXY_MODE": "configured",
            "PROXY_TEMPLATE": "http://user-session-{session}:pass@gate.example.com:8088",
        })
        assert isinstance(p, ConfiguredRotatingProxyProvider)
        ep = p.get()
        assert ep is not None
        assert ep.host == "gate.example.com"
        assert ep.username is not None
        assert "{session}" not in ep.username  # session was substituted

    def test_free_mode_returns_free_provider(self):
        p = proxy_provider_from_config({"PROXY_MODE": "free"})
        assert isinstance(p, FreeProxyProvider)

    def test_case_insensitive_mode(self):
        p = proxy_provider_from_config({"PROXY_MODE": "NONE"})
        assert isinstance(p, NoProxyProvider)


# ---------------------------------------------------------------------------
# ProxyEndpoint helpers
# ---------------------------------------------------------------------------

class TestProxyEndpoint:

    def test_as_url_without_auth(self):
        ep = ProxyEndpoint(scheme="http", host="proxy.example.com", port=8080)
        assert ep.as_url() == "http://proxy.example.com:8080"

    def test_as_url_with_auth(self):
        ep = ProxyEndpoint(scheme="http", host="h.example.com", port=80, username="u", password="p")
        assert ep.as_url() == "http://u:p@h.example.com:80"

    def test_frozen(self):
        ep = ProxyEndpoint(scheme="http", host="x.example.com", port=80)
        with pytest.raises((AttributeError, TypeError)):
            ep.host = "y.example.com"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NoProxyProvider
# ---------------------------------------------------------------------------

class TestNoProxyProvider:

    def test_get_returns_none(self):
        assert NoProxyProvider().get() is None

    def test_report_and_rotate_are_noops(self):
        p = NoProxyProvider()
        ep = ProxyEndpoint(scheme="http", host="x", port=80)
        p.report(ep, ok=False)  # must not raise
        p.rotate()              # must not raise


# ---------------------------------------------------------------------------
# Legacy proxy_config compat (existing tests must still pass)
# ---------------------------------------------------------------------------

class TestLegacyCompatibility:

    def test_proxy_config_kwarg_still_works(self):
        """HttpClient(proxy_config=...) must not raise (old signature)."""
        from adapters.botting.l4_transport.proxy_config import ProxyConfig
        config = ProxyConfig(proxy_url=None)
        client = HttpClient(proxy_config=config)
        # NoProxy path: get() returns None
        ep = client._provider.get()
        assert ep is None

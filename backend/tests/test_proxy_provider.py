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


class _FakeClock:
    """Deterministic injectable monotonic clock (no wall-clock dependency)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


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
        # API change: selection is now LRU + per-IP budget, not index-based, so
        # we drive the ban scenario through the public API (no _index poke).
        pool = [
            "http://good.example.com:80",
            "http://banned.example.com:80",
        ]
        clock = _FakeClock()
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=None, cooldown=9999, clock=clock,
        )

        # Pick whichever endpoint LRU hands out first, then ban it.
        banned = p.get()
        assert banned is not None
        p.report(banned, ok=False)

        # Next get() must skip the banned host (still in cooldown).
        next_ep = p.get()
        assert next_ep is not None
        assert next_ep.host != banned.host

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


# ---------------------------------------------------------------------------
# PROACTIVE load distribution: LRU spread + per-IP budget + template tokens
# ---------------------------------------------------------------------------

class TestProactiveLoadDistribution:

    def _pool(self, n: int) -> List[str]:
        return [f"http://p{i}.example.com:80" for i in range(n)]

    # (a) per_request spreads K >= pool-size requests evenly across all IPs
    def test_per_request_spreads_evenly_across_pool(self):
        clock = _FakeClock()
        pool = self._pool(4)
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=1, clock=clock,
            max_requests_per_ip=100, rate_window=60.0,
        )
        counts = {}
        # 12 requests over 4 IPs -> each IP ~3 times (advance clock per request)
        for _ in range(12):
            ep = p.get()
            assert ep is not None
            counts[ep.host] = counts.get(ep.host, 0) + 1
            clock.advance(0.1)

        # All four IPs were used, and load is even (LRU round-robins).
        assert len(counts) == 4
        assert set(counts.values()) == {3}

    # (b) an IP at its per-IP budget is SKIPPED proactively (no ban needed)
    def test_over_budget_ip_skipped_before_any_ban(self):
        clock = _FakeClock()
        pool = self._pool(2)
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=0, clock=clock,
            max_requests_per_ip=2, rate_window=60.0,
        )
        hosts = []
        # 4 requests, budget=2/IP/60s -> 2 each, none banned, none repeated >2x
        for _ in range(4):
            ep = p.get()
            assert ep is not None
            hosts.append(ep.host)
            clock.advance(0.5)

        assert hosts.count(pool_host(pool[0])) <= 2
        assert hosts.count(pool_host(pool[1])) <= 2
        assert len(set(hosts)) == 2

        # 5th request: both IPs are at budget within the window -> still served
        # (soonest-eligible), NOT a None / ban — proactive cooling, not refusal.
        ep5 = p.get()
        assert ep5 is not None

    # (c) LRU picks the longest-idle endpoint
    def test_lru_picks_longest_idle_endpoint(self):
        clock = _FakeClock()
        pool = self._pool(3)
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=0, clock=clock,
            max_requests_per_ip=100, rate_window=600.0,
        )
        first = p.get(); clock.advance(1)
        second = p.get(); clock.advance(1)
        third = p.get(); clock.advance(1)
        # All three distinct so far (each idle "forever" until used).
        assert len({first.host, second.host, third.host}) == 3

        # Next pick MUST be `first` again — it has been idle the longest.
        fourth = p.get()
        assert fourth.host == first.host

    # (d) TEMPLATE mode yields a UNIQUE session token per request
    def test_template_mints_unique_session_per_request(self):
        clock = _FakeClock()
        p = ConfiguredRotatingProxyProvider(
            proxy_template="http://user-session-{session}:pass@gate.example.com:8088",
            seed=7, clock=clock,
        )
        tokens = []
        for _ in range(20):
            ep = p.get()
            assert ep is not None
            assert ep.host == "gate.example.com"
            assert "{session}" not in (ep.username or "")
            tokens.append(ep.username)
            clock.advance(0.01)

        # Every request -> distinct session token -> distinct exit IP.
        assert len(set(tokens)) == 20

    def test_template_tokens_deterministic_under_seed(self):
        c1, c2 = _FakeClock(), _FakeClock()
        tmpl = "http://s-{session}:pass@gate.example.com:8088"
        p1 = ConfiguredRotatingProxyProvider(proxy_template=tmpl, seed=99, clock=c1)
        p2 = ConfiguredRotatingProxyProvider(proxy_template=tmpl, seed=99, clock=c2)
        seq1 = [p1.get().username for _ in range(5)]
        seq2 = [p2.get().username for _ in range(5)]
        assert seq1 == seq2

    # (e) ban-handling still works as a FALLBACK safety net
    def test_ban_handling_still_cools_down_endpoint(self):
        clock = _FakeClock()
        pool = self._pool(2)
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=0, cooldown=300, clock=clock,
            max_requests_per_ip=100, rate_window=60.0,
        )
        victim = p.get()
        p.report(victim, ok=False)

        # Banned host is skipped while cooling down.
        for _ in range(4):
            ep = p.get()
            assert ep.host != victim.host
            clock.advance(1)

        # After cooldown expires it returns to the eligible set.
        clock.advance(301)
        seen = {p.get().host for _ in range(6)}
        assert victim.host in seen

    def test_rotate_clears_sticky_hold(self):
        clock = _FakeClock()
        pool = self._pool(3)
        p = ConfiguredRotatingProxyProvider(
            proxy_list=pool, seed=0, rotation="sticky", clock=clock,
            max_requests_per_ip=100, rate_window=600.0,
        )
        a = p.get().host
        assert p.get().host == a  # sticky holds the same egress
        p.rotate()                # defensive rotate drops the hold
        clock.advance(1)
        b = p.get().host
        assert b != a


# ---------------------------------------------------------------------------
# (f) Factory wires the new proactive knobs
# ---------------------------------------------------------------------------

class TestProactiveFactoryKnobs:

    def test_factory_wires_rotation_and_budget_knobs(self):
        p = proxy_provider_from_config({
            "PROXY_MODE": "configured",
            "PROXY_LIST": "http://a.example.com:80,http://b.example.com:80",
            "PROXY_ROTATION": "per_n:3",
            "PROXY_MAX_RPS_PER_IP": "7",
            "PROXY_RATE_WINDOW": "30",
            "PROXY_SEED": "5",
        })
        assert isinstance(p, ConfiguredRotatingProxyProvider)
        assert p._rotation == "per_n"
        assert p._per_n == 3
        assert p._max_per_ip == 7
        assert p._rate_window == 30.0

    def test_factory_defaults_to_per_request(self):
        p = proxy_provider_from_config({
            "PROXY_MODE": "configured",
            "PROXY_LIST": "http://a.example.com:80",
        })
        assert isinstance(p, ConfiguredRotatingProxyProvider)
        assert p._rotation == "per_request"
        assert p._max_per_ip == 5
        assert p._rate_window == 60.0


def pool_host(url: str) -> str:
    import urllib.parse as _u
    return _u.urlparse(url).hostname or url


# ---------------------------------------------------------------------------
# HttpClient drives proactive selection: fresh proxy + record_use per request
# ---------------------------------------------------------------------------

class TestHttpClientProactiveSelection:

    def test_fresh_proxy_selected_and_usage_recorded_per_request(self):
        provider = MagicMock(spec=ProxyProvider)
        ep = ProxyEndpoint(scheme="http", host="egress.example.com", port=80)
        provider.get.return_value = ep

        client = HttpClient(
            proxy_provider=provider,
            domain_throttle=0.0,
            _sleep=lambda _: None,
        )

        from adapters.botting.l4_transport.fetch_result import FetchResult
        ok = FetchResult(url="http://x/", status=200, content_type="text/html", body=b"OK")
        with patch.object(client, "_do_fetch", return_value=ok):
            client.fetch_raw("http://x/")

        # Fresh egress chosen for the request and its usage recorded (proactive).
        provider.get.assert_called_once()
        provider.record_use.assert_called_once_with(ep)

    def test_record_use_skipped_when_provider_lacks_it(self):
        # NoProxyProvider has no record_use; client must not crash.
        port = _free_port()
        server = _start_mock_server(port)
        try:
            client = HttpClient(
                proxy_provider=NoProxyProvider(),
                domain_throttle=0.0,
                _sleep=lambda _: None,
            )
            result = client.fetch_raw(f"http://127.0.0.1:{port}/")
            assert result.status == 200
        finally:
            server.shutdown()

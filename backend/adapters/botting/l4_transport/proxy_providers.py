"""Concrete ProxyProvider adapters + factory.

PROXY_MODE environment / config key selects the implementation:
  none        -> NoProxyProvider      (direct connection, default)
  free        -> FreeProxyProvider    (wraps FreeProxyManager)
  configured  -> ConfiguredRotatingProxyProvider (BYO rotating list / template)
  simulated   -> SimulatedProxyProvider (wraps ThreadedProxyServer for tests)

BYO credentials are supplied via config dict or environment variables:
  PROXY_LIST  = comma-separated list of "scheme://[user:pass@]host:port" strings
  PROXY_TEMPLATE = URL template with {session} placeholder, e.g.
                   "http://user-session-{session}:pass@gate.example.com:8088"

Design: all state is instance-level; no global singletons (tests can instantiate
fresh objects). Thread-safe via threading.Lock on mutable fields.
"""
from __future__ import annotations

import os
import random
import threading
import time
import urllib.parse
from typing import Dict, List, Optional

from adapters.botting.l4_transport.proxy_provider import ProxyEndpoint, ProxyProvider


# ---------------------------------------------------------------------------
# NoProxyProvider — direct connection (default)
# ---------------------------------------------------------------------------

class NoProxyProvider:
    """Always returns None — HttpClient uses a direct connection."""

    def get(self) -> Optional[ProxyEndpoint]:
        return None

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        pass  # nothing to track

    def rotate(self) -> None:
        pass


# ---------------------------------------------------------------------------
# FreeProxyProvider — wraps the existing FreeProxyManager
# ---------------------------------------------------------------------------

class FreeProxyProvider:
    """Delegates to FreeProxyManager; tracks bans in a local cooldown set."""

    _COOLDOWN_SECONDS = 120

    def __init__(self) -> None:
        from adapters.botting.l4_transport.proxy_config import FreeProxyManager
        self._manager = FreeProxyManager()
        self._lock = threading.Lock()
        self._cooldown: Dict[str, float] = {}  # proxy_url -> expiry timestamp

    def _is_cooled_down(self, url: str) -> bool:
        expiry = self._cooldown.get(url, 0.0)
        return time.time() < expiry

    def get(self) -> Optional[ProxyEndpoint]:
        # Try up to len(proxies) times to skip cooled-down entries
        with self._manager.lock:
            pool = list(self._manager.proxies)

        for _ in range(max(len(pool), 1)):
            raw = self._manager.get_proxy()
            if raw is None:
                return None
            if not self._is_cooled_down(raw):
                return _parse_url(raw)
        return None  # all proxies in cooldown

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        if not ok:
            url = endpoint.as_url()
            with self._lock:
                self._cooldown[url] = time.time() + self._COOLDOWN_SECONDS

    def rotate(self) -> None:
        # FreeProxyManager already round-robins on each get_proxy() call; no-op here
        pass


# ---------------------------------------------------------------------------
# ConfiguredRotatingProxyProvider — BYO paid / residential proxy list
# ---------------------------------------------------------------------------

class ConfiguredRotatingProxyProvider:
    """Rotates through a caller-supplied list of endpoints.

    Config options (all optional, merged from kwargs then env):
      proxy_list      List[str]  — pre-parsed list of proxy URL strings
      proxy_template  str        — URL with {session} placeholder; each rotation
                                   generates a new session suffix
      seed            int        — seed for deterministic ordering in tests
      cooldown        int        — seconds to skip a banned endpoint (default 120)
    """

    _DEFAULT_COOLDOWN = 120

    def __init__(
        self,
        proxy_list: Optional[List[str]] = None,
        proxy_template: Optional[str] = None,
        seed: Optional[int] = None,
        cooldown: int = _DEFAULT_COOLDOWN,
    ) -> None:
        raw_list = proxy_list or []
        if not raw_list:
            env_list = os.environ.get("PROXY_LIST", "")
            if env_list:
                raw_list = [p.strip() for p in env_list.split(",") if p.strip()]

        self._template = proxy_template or os.environ.get("PROXY_TEMPLATE")
        self._cooldown_seconds = cooldown
        self._lock = threading.Lock()
        self._cooldown: Dict[str, float] = {}  # proxy_url -> expiry

        rng = random.Random(seed)
        self._pool: List[str] = list(raw_list)
        if seed is not None:
            rng.shuffle(self._pool)

        self._index = 0
        self._rng = rng

    # ------------------------------------------------------------------
    def _next_from_pool(self) -> Optional[str]:
        """Advance index, skip cooled-down entries."""
        if not self._pool:
            return None
        n = len(self._pool)
        for _ in range(n):
            url = self._pool[self._index % n]
            self._index += 1
            if not self._is_cooled_down(url):
                return url
        return None  # all banned

    def _is_cooled_down(self, url: str) -> bool:
        return time.time() < self._cooldown.get(url, 0.0)

    def _template_endpoint(self) -> Optional[ProxyEndpoint]:
        if not self._template:
            return None
        session = self._rng.randint(0, 0xFFFF)
        url = self._template.replace("{session}", f"{session:04x}")
        return _parse_url(url)

    # ------------------------------------------------------------------
    def get(self) -> Optional[ProxyEndpoint]:
        with self._lock:
            raw = self._next_from_pool()
            if raw:
                return _parse_url(raw)
            return self._template_endpoint()

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        if not ok:
            url = endpoint.as_url()
            with self._lock:
                self._cooldown[url] = time.time() + self._cooldown_seconds

    def rotate(self) -> None:
        with self._lock:
            if self._pool:
                self._index += 1


# ---------------------------------------------------------------------------
# SimulatedProxyProvider — wraps ThreadedProxyServer (deterministic tests)
# ---------------------------------------------------------------------------

class SimulatedProxyProvider:
    """Starts (or reuses) a local ThreadedProxyServer on a fixed/random port.

    The server is launched in a daemon thread so it dies with the test process.
    Pass an explicit port to get deterministic addresses; omit for auto-assign.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8088) -> None:
        import socket as _socket
        from adapters.botting.l4_transport.simulated_proxy_server import ThreadedProxyServer

        if port == 0:
            # Auto-assign a free port
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                port = s.getsockname()[1]

        self._endpoint = ProxyEndpoint(scheme="http", host=host, port=port)
        self._server = ThreadedProxyServer(host, port)
        self._started = False
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._lock:
            if not self._started:
                import threading as _threading
                t = _threading.Thread(target=self._server.start, daemon=True)
                t.start()
                time.sleep(0.05)  # give the server socket time to bind
                self._started = True

    def get(self) -> Optional[ProxyEndpoint]:
        self._ensure_started()
        return self._endpoint

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        pass  # simulated server is always "healthy" in tests

    def rotate(self) -> None:
        pass  # single endpoint; nothing to rotate

    def stop(self) -> None:
        """Cleanly close the server socket (call from test teardown)."""
        try:
            self._server.server_socket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def proxy_provider_from_config(config: Optional[dict] = None) -> ProxyProvider:
    """Return the right ProxyProvider based on PROXY_MODE in *config* or env.

    config keys (all optional):
      PROXY_MODE      : none | free | configured | simulated  (default: none)
      PROXY_LIST      : comma-separated proxy URLs (for 'configured')
      PROXY_TEMPLATE  : URL template with {session} (for 'configured')
      PROXY_SEED      : int seed for deterministic rotation (for 'configured')
      PROXY_COOLDOWN  : seconds to cool-down a banned endpoint (default 120)
      PROXY_SIM_HOST  : host for simulated server (default 127.0.0.1)
      PROXY_SIM_PORT  : port for simulated server (default 8088)
    """
    cfg = config or {}

    def _get(key: str, default: str = "") -> str:
        return cfg.get(key) or os.environ.get(key, default)

    mode = _get("PROXY_MODE", "none").lower().strip()

    if mode == "free":
        return FreeProxyProvider()

    if mode == "configured":
        raw_list_str = _get("PROXY_LIST", "")
        proxy_list = [p.strip() for p in raw_list_str.split(",") if p.strip()] if raw_list_str else []
        template = _get("PROXY_TEMPLATE") or None
        seed_str = _get("PROXY_SEED", "")
        seed = int(seed_str) if seed_str.strip().lstrip("-").isdigit() else None
        cooldown = int(_get("PROXY_COOLDOWN", "120"))
        return ConfiguredRotatingProxyProvider(
            proxy_list=proxy_list,
            proxy_template=template,
            seed=seed,
            cooldown=cooldown,
        )

    if mode == "simulated":
        host = _get("PROXY_SIM_HOST", "127.0.0.1")
        port = int(_get("PROXY_SIM_PORT", "8088"))
        return SimulatedProxyProvider(host=host, port=port)

    # default: none
    return NoProxyProvider()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_url(url: str) -> ProxyEndpoint:
    """Parse a proxy URL string into a ProxyEndpoint."""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if scheme == "https" else 80)
    username = parsed.username or None
    password = parsed.password or None
    return ProxyEndpoint(scheme=scheme, host=host, port=port, username=username, password=password)

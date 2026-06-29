"""HttpClient — OSI Layer 4 transport with header realism, proxy rotation, and ban handling.

Key capabilities added on top of Worker 1's fetch_raw/fetch split:
  - Realistic browser headers (UA, Accept, Accept-Language, Accept-Encoding, DNT)
  - ProxyProvider integration: on 403/429, reports ban, rotates, backs off, retries
  - Per-domain throttle: enforces a minimum gap between consecutive hits to the same host
  - All sleep calls go through a swappable _sleep callable so tests can inject a no-op
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPPasswordMgrWithDefaultRealm,
    ProxyBasicAuthHandler,
    ProxyHandler,
    build_opener,
    urlopen,  # kept as module-level name so test patches still resolve
)

from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.fetch_result import FetchResult
from adapters.botting.l4_transport.proxy_provider import ProxyEndpoint, ProxyProvider
from adapters.botting.l4_transport.proxy_providers import NoProxyProvider

# ---------------------------------------------------------------------------
# Realistic browser headers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_RETRY_STATUSES = {403, 429}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0   # seconds; actual = base * 2^attempt
_DOMAIN_THROTTLE_SECONDS = 1.0  # minimum gap between hits to the same host


class HttpClient(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Physical network communication and basic HTTP.

    Args:
        proxy_provider: Implementation of the ProxyProvider port.
            Defaults to NoProxyProvider (direct connection).
        extra_headers: Additional/override HTTP headers to send with every request.
        max_retries: How many times to retry on 403/429 before giving up.
        domain_throttle: Minimum seconds between consecutive requests to the same host.
        _sleep: Injectable sleep function — replace with a no-op in tests.

    Legacy compat: still accepts proxy_config= keyword for backward compat with
    existing tests that pass a ProxyConfig object.
    """

    def __init__(
        self,
        proxy_provider: Optional[ProxyProvider] = None,
        extra_headers: Optional[dict[str, str]] = None,
        max_retries: int = _MAX_RETRIES,
        domain_throttle: float = _DOMAIN_THROTTLE_SECONDS,
        _sleep: Callable[[float], None] = time.sleep,
        # Legacy compat
        proxy_config=None,
    ) -> None:
        # Legacy path: wrap old ProxyConfig into a thin adapter so old tests pass unchanged
        if proxy_provider is None and proxy_config is not None:
            proxy_provider = _LegacyProxyConfigAdapter(proxy_config)

        self._provider: ProxyProvider = proxy_provider or NoProxyProvider()
        self._headers = dict(_DEFAULT_HEADERS)
        if extra_headers:
            self._headers.update(extra_headers)
        self._max_retries = max_retries
        self._domain_throttle = domain_throttle
        self._sleep = _sleep
        self._last_hit: dict[str, float] = {}  # host -> last request timestamp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_raw(self, url: str) -> FetchResult:
        """Fetch URL as raw bytes — never crashes on binary content (e.g. PDFs).

        On 403/429: reports ban to provider, rotates, applies exponential backoff,
        and retries up to max_retries times.
        """
        self._throttle(url)
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            # PROACTIVE rotation: a fresh egress is selected for EVERY request so
            # load spreads across the pool and each IP stays low-rate — we do NOT
            # wait for a ban to rotate. The ban-handling below is only a fallback.
            endpoint: Optional[ProxyEndpoint] = self._provider.get()
            self._mark_used(endpoint)
            try:
                result = self._do_fetch(url, endpoint)
                # Record successful fetch for per-domain throttle
                self._record_hit(url)
                if endpoint is not None:
                    self._provider.report(endpoint, ok=True)
                return result
            except _BanError as e:
                last_exc = e
                if endpoint is not None:
                    self._provider.report(endpoint, ok=False)
                    self._provider.rotate()
                if attempt < self._max_retries:
                    backoff = _BACKOFF_BASE * (2 ** attempt)
                    self._sleep(backoff)
            except (URLError, OSError) as e:
                # Network-level failure — don't retry as "ban"
                raise RuntimeError(f"Network error fetching {url}: {e}") from e

        raise RuntimeError(
            f"Gave up fetching {url} after {self._max_retries} retries "
            f"(last status: {last_exc})"
        )

    def fetch(self, url: str) -> str:
        """Fetch raw HTML/text from a URL (satisfies HtmlFetcherPort contract)."""
        result = self.fetch_raw(url)
        try:
            return result.text
        except ValueError:
            return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self, url: str) -> None:
        """Block briefly if we hit the same host too fast."""
        host = _host(url)
        last = self._last_hit.get(host, 0.0)
        gap = time.time() - last
        if gap < self._domain_throttle:
            self._sleep(self._domain_throttle - gap)

    def _record_hit(self, url: str) -> None:
        self._last_hit[_host(url)] = time.time()

    def _mark_used(self, endpoint: Optional[ProxyEndpoint]) -> None:
        """Tell usage-aware providers that *endpoint* was just selected.

        Lets the provider keep its LRU + per-IP rate budget current so it can
        proactively spread load. Optional on the Protocol — skipped silently for
        providers (NoProxy, Simulated) that don't implement it.
        """
        if endpoint is None:
            return
        record_use = getattr(self._provider, "record_use", None)
        if callable(record_use):
            record_use(endpoint)

    def _do_fetch(self, url: str, endpoint: Optional[ProxyEndpoint]) -> FetchResult:
        """Single HTTP attempt via *endpoint* (or direct if None)."""
        handlers = []

        if endpoint:
            proxy_url = endpoint.as_url()
            parsed = urllib.parse.urlparse(proxy_url)
            proxy_server = (
                f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                if parsed.port
                else f"{parsed.scheme}://{parsed.hostname}"
            )
            proxy_handler = ProxyHandler({"http": proxy_server, "https": proxy_server})
            handlers.append(proxy_handler)

            if parsed.username and parsed.password:
                password_mgr = HTTPPasswordMgrWithDefaultRealm()
                password_mgr.add_password(None, proxy_server, parsed.username, parsed.password)
                auth_handler = ProxyBasicAuthHandler(password_mgr)
                handlers.append(auth_handler)

        try:
            if handlers:
                # Proxy path: build a custom opener with proxy handlers
                opener = build_opener(*handlers)
                opener.addheaders = list(self._headers.items())
                ctx = opener.open(url, timeout=15)
            else:
                # Direct path: use module-level urlopen so test patches can intercept it
                req = urllib.request.Request(url, headers=self._headers)
                ctx = urlopen(req, timeout=15)

            with ctx as response:
                body = response.read()
                content_encoding = response.headers.get("Content-Encoding", "").lower()
                if "gzip" in content_encoding:
                    import gzip
                    try:
                        body = gzip.decompress(body)
                    except Exception:
                        pass
                elif "deflate" in content_encoding:
                    import zlib
                    try:
                        body = zlib.decompress(body)
                    except Exception:
                        pass
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                status = response.status
            return FetchResult(url=url, status=status, content_type=content_type, body=body)
        except HTTPError as e:
            if e.code in _RETRY_STATUSES:
                raise _BanError(e.code, url) from e
            raise RuntimeError(f"HTTP {e.code} fetching {url}") from e


# ---------------------------------------------------------------------------
# Internal exception for ban/block responses
# ---------------------------------------------------------------------------

class _BanError(Exception):
    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} (ban/block) from {url}")
        self.status = status


# ---------------------------------------------------------------------------
# Legacy adapter so old ProxyConfig-based tests don't break
# ---------------------------------------------------------------------------

class _LegacyProxyConfigAdapter:
    """Thin shim: wraps a ProxyConfig as a ProxyProvider."""

    def __init__(self, proxy_config) -> None:
        self._config = proxy_config

    def get(self) -> Optional[ProxyEndpoint]:
        raw = self._config.get_active_proxy_url()
        if not raw:
            return None
        from adapters.botting.l4_transport.proxy_providers import _parse_url
        return _parse_url(raw)

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        pass  # ProxyConfig has no health tracking

    def rotate(self) -> None:
        pass  # rotation is handled inside ProxyConfig.get_active_proxy_url()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _host(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or url

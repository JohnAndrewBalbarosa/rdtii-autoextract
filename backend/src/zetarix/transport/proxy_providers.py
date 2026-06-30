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

import itertools
import os
import random
import threading
import time
import urllib.parse
from typing import Callable, Deque, Dict, List, Optional
from collections import deque

from zetarix.transport.proxy_provider import ProxyEndpoint, ProxyProvider
from zetarix.transport.proxy_pool_broker import (
    ProxyLease,
    ProxyPoolBroker,
    PoolExhausted,
)


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
        from zetarix.transport.proxy_config import FreeProxyManager
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
    """Proactive load-distribution proxy provider (BYO list / residential template).

    Strategy is PROACTIVE, not reactive: instead of hammering one IP until the
    server bans it and only then rotating, we spread requests across the egress
    pool so each IP carries few, low-rate hits and looks like a separate ordinary
    visitor. Ban-handling (report/rotate) remains only as a defensive safety net
    that should now rarely fire.

    Two mechanisms cooperate:

      1. Fixed proxy LIST: a fresh egress is chosen per request using
         least-recently-used (LRU) selection — the endpoint idle longest wins —
         so load stays even. A per-IP rate budget (`max_requests_per_ip` within
         `rate_window` seconds) proactively SKIPS an endpoint *before* any server
         pushback; if every endpoint is momentarily over budget the soonest-
         eligible one is picked.

      2. Rotating-residential TEMPLATE: when `proxy_template` carries a
         `{session}` placeholder we mint a UNIQUE session token per request via a
         seeded, injectable counter. Distinct tokens => distinct exit IPs => the
         gateway makes us look like many ordinary users, not one spammer.

    Config options (all optional, merged from kwargs then env):
      proxy_list           List[str]  pre-parsed list of proxy URL strings
      proxy_template       str        URL with {session} placeholder (per-request token)
      seed                 int        seed for deterministic ordering/tokens in tests
      cooldown             int        seconds to skip a BANNED endpoint (default 120)
      rotation             str        'per_request' (default) | 'per_n:<k>' | 'sticky'
      max_requests_per_ip  int        per-IP rate budget within rate_window (default 5)
      rate_window          float      sliding window seconds for the budget (default 60.0)
      clock                callable   injected monotonic clock -> float (tests)
    """

    _DEFAULT_COOLDOWN = 120
    _DEFAULT_MAX_RPS_PER_IP = 5      # max hits one egress IP may take per window
    _DEFAULT_RATE_WINDOW = 60.0     # sliding window (seconds) for the budget
    _DEFAULT_ROTATION = "per_request"

    def __init__(
        self,
        proxy_list: Optional[List[str]] = None,
        proxy_template: Optional[str] = None,
        seed: Optional[int] = None,
        cooldown: int = _DEFAULT_COOLDOWN,
        rotation: str = _DEFAULT_ROTATION,
        max_requests_per_ip: int = _DEFAULT_MAX_RPS_PER_IP,
        rate_window: float = _DEFAULT_RATE_WINDOW,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        raw_list = proxy_list or []
        if not raw_list:
            env_list = os.environ.get("PROXY_LIST", "")
            if env_list:
                raw_list = [p.strip() for p in env_list.split(",") if p.strip()]

        self._template = proxy_template or os.environ.get("PROXY_TEMPLATE")
        self._cooldown_seconds = cooldown
        self._max_per_ip = max(1, int(max_requests_per_ip))
        self._rate_window = float(rate_window)
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        self._cooldown: Dict[str, float] = {}       # proxy_url -> ban expiry (clock units)
        self._last_used: Dict[str, float] = {}      # proxy_url -> last selection time (LRU)
        self._recent: Dict[str, Deque[float]] = {}  # proxy_url -> recent use timestamps

        # rotation policy: per_request | sticky | per_n:<k>
        self._rotation, self._per_n = _parse_rotation(rotation)
        self._sticky_url: Optional[str] = None  # for sticky / per_n hold
        self._sticky_remaining = 0

        rng = random.Random(seed)
        self._pool: List[str] = list(raw_list)
        if seed is not None:
            rng.shuffle(self._pool)

        # Seeded, injectable counter -> unique {session} token per request.
        self._session_counter = itertools.count(rng.randint(0, 0xFFFF))
        self._rng = rng

    # ------------------------------------------------------------------
    # Eligibility / budget helpers (call under self._lock)
    # ------------------------------------------------------------------
    def _is_cooled_down(self, url: str, now: float) -> bool:
        """True if *url* is still serving a ban cooldown (defensive net)."""
        return now < self._cooldown.get(url, 0.0)

    def _prune_recent(self, url: str, now: float) -> Deque[float]:
        dq = self._recent.setdefault(url, deque())
        cutoff = now - self._rate_window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        return dq

    def _over_budget(self, url: str, now: float) -> bool:
        """Proactive skip: True if using *url* now exceeds its per-IP rate budget."""
        return len(self._prune_recent(url, now)) >= self._max_per_ip

    def _earliest_eligible_time(self, url: str, now: float) -> float:
        """When *url* next drops under budget (for soonest-eligible fallback)."""
        dq = self._prune_recent(url, now)
        if len(dq) < self._max_per_ip:
            return now
        # the oldest in-window hit must age out of the window
        return dq[0] + self._rate_window

    def _record_use_locked(self, url: str, now: float) -> None:
        self._last_used[url] = now
        self._prune_recent(url, now).append(now)

    # ------------------------------------------------------------------
    # LRU + budget selection over the fixed list (call under self._lock)
    # ------------------------------------------------------------------
    def _select_from_pool(self, now: float) -> Optional[str]:
        if not self._pool:
            return None

        # Sticky / per_n: keep the held endpoint while it stays eligible.
        if self._rotation != "per_request" and self._sticky_url is not None:
            held = self._sticky_url
            if (
                self._sticky_remaining > 0
                and not self._is_cooled_down(held, now)
                and not self._over_budget(held, now)
            ):
                self._sticky_remaining -= 1
                return held
            self._sticky_url = None  # fall through to pick a fresh one

        # Candidates that are neither banned nor over their per-IP budget.
        eligible = [
            u for u in self._pool
            if not self._is_cooled_down(u, now) and not self._over_budget(u, now)
        ]
        if eligible:
            # LRU: pick the endpoint idle the longest (never used == idle forever).
            chosen = min(eligible, key=lambda u: self._last_used.get(u, float("-inf")))
        else:
            # Everyone momentarily over budget (and not banned): soonest-eligible.
            usable = [u for u in self._pool if not self._is_cooled_down(u, now)]
            if not usable:
                return None  # whole pool banned -> caller falls back to template
            chosen = min(usable, key=lambda u: self._earliest_eligible_time(u, now))

        if self._rotation != "per_request":
            self._sticky_url = chosen
            self._sticky_remaining = max(0, self._per_n - 1)
        return chosen

    def _template_endpoint(self) -> Optional[ProxyEndpoint]:
        """Mint a UNIQUE {session} token per request -> new exit IP each call."""
        if not self._template:
            return None
        session = next(self._session_counter)
        url = self._template.replace("{session}", f"{session:08x}")
        return _parse_url(url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self) -> Optional[ProxyEndpoint]:
        with self._lock:
            now = self._clock()
            raw = self._select_from_pool(now)
            if raw:
                self._record_use_locked(raw, now)
                return _parse_url(raw)
            # No list (or whole pool banned): residential template path.
            return self._template_endpoint()

    def record_use(self, endpoint: ProxyEndpoint) -> None:
        """Optional hook: refresh LRU + budget if HttpClient selects out-of-band.

        get() already records usage, so this is idempotent-ish; it exists so the
        transport layer can mark usage for endpoints minted elsewhere (template).
        """
        url = endpoint.as_url()
        with self._lock:
            # Only track endpoints we actually manage in the fixed pool; template
            # endpoints are unique per request so tracking them is pointless.
            if url in self._pool:
                self._record_use_locked(url, self._clock())

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        if not ok:
            url = endpoint.as_url()
            with self._lock:
                self._cooldown[url] = self._clock() + self._cooldown_seconds

    def rotate(self) -> None:
        with self._lock:
            # Drop any sticky hold so the next get() re-selects via LRU/budget.
            self._sticky_url = None
            self._sticky_remaining = 0


# ---------------------------------------------------------------------------
# BrokeredProxyProvider — per-thread view over a SHARED ProxyPoolBroker
# ---------------------------------------------------------------------------

class BrokeredProxyProvider:
    """Adapter that lets per-thread HttpClients share ONE coordinated pool.

    Each HttpClient keeps its own ProxyProvider, but here every instance (or, in
    the common case, one instance shared across threads) talks to the SAME
    ``ProxyPoolBroker``. The broker is the middleman that guarantees two workers
    never hold the same egress IP at once, fixing the "we rotate but still look
    like one spammy IP" problem.

    Lease lifecycle is keyed by worker (thread) id: ``get()`` releases the
    calling worker's PREVIOUS lease and acquires a fresh, non-colliding one, so
    a crawler that calls get() once per request keeps rotating coordinated IPs
    without ever double-booking. Call ``release()`` when a worker is done so the
    IP returns to the pool for others.

    NOTE: For rotating-residential TEMPLATE mode, a per-request unique
    ``{session}`` token already yields a distinct exit IP per call, so
    collisions cannot happen there — the broker is specifically for FIXED/finite
    IP LISTS where the same handful of IPs is reused.
    """

    _DEFAULT_ACQUIRE_TIMEOUT = 30.0

    def __init__(
        self,
        broker: ProxyPoolBroker,
        cooldown: int = 120,
        acquire_timeout: Optional[float] = _DEFAULT_ACQUIRE_TIMEOUT,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._broker = broker
        self._cooldown_seconds = cooldown
        self._acquire_timeout = acquire_timeout
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        # Active lease per worker (thread) id so get() can release the previous.
        self._active: Dict[int, ProxyLease] = {}
        self._cooldown: Dict[str, float] = {}  # proxy_url -> ban expiry

    def _worker_id(self, worker_id: Optional[int]) -> int:
        return worker_id if worker_id is not None else threading.get_ident()

    def get(self, worker_id: Optional[int] = None) -> Optional[ProxyEndpoint]:
        """Release this worker's previous lease, acquire a fresh coordinated IP.

        Returns None only if the underlying pool is empty / everything timed out
        — the caller (HttpClient) then falls back to a direct connection.
        """
        wid = self._worker_id(worker_id)
        with self._lock:
            prev = self._active.pop(wid, None)
        if prev is not None:
            self._broker.release(prev)

        # Skip endpoints still serving a ban cooldown by re-leasing past them.
        attempts = max(self._broker.size, 1)
        lease: Optional[ProxyLease] = None
        for _ in range(attempts):
            try:
                candidate = self._broker.acquire(
                    worker_id=wid, timeout=self._acquire_timeout
                )
            except PoolExhausted:
                return None
            if not self._is_cooled_down(candidate.endpoint):
                lease = candidate
                break
            # Cooled-down: hold nothing, release and try the next distinct IP.
            self._broker.release(candidate)
        if lease is None:
            return None
        with self._lock:
            self._active[wid] = lease
        return lease.endpoint

    def release(self, worker_id: Optional[int] = None) -> None:
        """Return the calling worker's leased IP to the shared pool."""
        wid = self._worker_id(worker_id)
        with self._lock:
            lease = self._active.pop(wid, None)
        if lease is not None:
            self._broker.release(lease)

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        """Cool a bad IP so subsequent get() calls skip it for a while."""
        if not ok:
            with self._lock:
                self._cooldown[endpoint.as_url()] = (
                    self._clock() + self._cooldown_seconds
                )

    def rotate(self) -> None:
        """Drop the current worker's lease so the next get() picks a new IP."""
        self.release()

    def reset(self, worker_id: Optional[int] = None) -> None:
        """Recycle a worker: release its lease and clear its broker history.

        Passthrough to ``ProxyPoolBroker.reset`` so the worker becomes "fresh,
        like new" and can rotate the FULL pool again on its next get()/acquire.
        """
        wid = self._worker_id(worker_id)
        # Return any held IP first so reset truly starts a clean cycle.
        self.release(wid)
        self._broker.reset(wid)

    def record_use(self, endpoint: ProxyEndpoint) -> None:  # pragma: no cover
        # The broker already records last_used at acquire-time; nothing to do.
        pass

    def _is_cooled_down(self, endpoint: ProxyEndpoint) -> bool:
        with self._lock:
            expiry = self._cooldown.get(endpoint.as_url(), 0.0)
        return self._clock() < expiry


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
        from zetarix.transport.simulated_proxy_server import ThreadedProxyServer

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
      PROXY_MODE      : none | free | configured | brokered | simulated  (default: none)
      PROXY_COORDINATED : 1/true -> force brokered mode regardless of PROXY_MODE
      PROXY_LIST      : comma-separated proxy URLs (for 'configured' / 'brokered')
      PROXY_TEMPLATE  : URL template with {session} (for 'configured')
      PROXY_SEED      : int seed for deterministic rotation (for 'configured')
      PROXY_COOLDOWN  : seconds to cool-down a banned endpoint (default 120)
      PROXY_ROTATION  : per_request (default) | per_n:<k> | sticky (for 'configured')
      PROXY_MAX_RPS_PER_IP : per-IP rate budget within the window (default 5)
      PROXY_RATE_WINDOW    : sliding window seconds for the budget (default 60)
      PROXY_SIM_HOST  : host for simulated server (default 127.0.0.1)
      PROXY_SIM_PORT  : port for simulated server (default 8088)
    """
    cfg = config or {}

    def _get(key: str, default: str = "") -> str:
        return cfg.get(key) or os.environ.get(key, default)

    mode = _get("PROXY_MODE", "none").lower().strip()
    coordinated = _get("PROXY_COORDINATED", "").strip().lower() in {"1", "true", "yes"}

    # Coordinated/brokered mode: one shared ProxyPoolBroker hands out
    # non-colliding IPs to all parallel workers over the FIXED PROXY_LIST.
    if mode == "brokered" or coordinated:
        raw_list_str = _get("PROXY_LIST", "")
        proxy_list = [p.strip() for p in raw_list_str.split(",") if p.strip()] if raw_list_str else []
        cooldown = int(_get("PROXY_COOLDOWN", "120"))
        broker = ProxyPoolBroker(proxy_list)
        return BrokeredProxyProvider(broker, cooldown=cooldown)

    if mode == "free":
        return FreeProxyProvider()

    if mode == "configured":
        raw_list_str = _get("PROXY_LIST", "")
        proxy_list = [p.strip() for p in raw_list_str.split(",") if p.strip()] if raw_list_str else []
        template = _get("PROXY_TEMPLATE") or None
        seed_str = _get("PROXY_SEED", "")
        seed = int(seed_str) if seed_str.strip().lstrip("-").isdigit() else None
        cooldown = int(_get("PROXY_COOLDOWN", "120"))
        rotation = _get("PROXY_ROTATION", "per_request")
        max_per_ip = int(_get("PROXY_MAX_RPS_PER_IP", "5"))
        rate_window = float(_get("PROXY_RATE_WINDOW", "60"))
        return ConfiguredRotatingProxyProvider(
            proxy_list=proxy_list,
            proxy_template=template,
            seed=seed,
            cooldown=cooldown,
            rotation=rotation,
            max_requests_per_ip=max_per_ip,
            rate_window=rate_window,
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

def _parse_rotation(rotation: str) -> tuple[str, int]:
    """Parse the PROXY_ROTATION knob into (policy, n).

    Accepts 'per_request' (default), 'sticky', or 'per_n:<k>'. Unknown values
    fall back to per_request. Returns the policy name plus the hold count n
    (1 for per_request/sticky-by-1, k for per_n:<k>).
    """
    value = (rotation or "per_request").strip().lower()
    if value.startswith("per_n:"):
        suffix = value.split(":", 1)[1].strip()
        n = int(suffix) if suffix.lstrip("-").isdigit() else 1
        return ("per_n", max(1, n))
    if value == "sticky":
        # sticky == hold one egress as long as it stays eligible
        return ("sticky", 10 ** 9)
    return ("per_request", 1)


def _parse_url(url: str) -> ProxyEndpoint:
    """Parse a proxy URL string into a ProxyEndpoint."""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if scheme == "https" else 80)
    username = parsed.username or None
    password = parsed.password or None
    return ProxyEndpoint(scheme=scheme, host=host, port=port, username=username, password=password)

"""ProxyProvider port + ProxyEndpoint dataclass.

This module is deliberately import-clean: no web, LLM, or pipeline deps.
Only stdlib + typing, so it can be safely imported anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProxyEndpoint:
    """Immutable description of a single proxy server."""

    scheme: str          # "http" or "socks5"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    def as_url(self) -> str:
        """Return the full proxy URL string."""
        if self.username and self.password:
            return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"


@runtime_checkable
class ProxyProvider(Protocol):
    """Port: yields proxy endpoints, tracks health, and rotates on demand.

    Implementations choose between no-proxy, free-list, configured rotating,
    or simulated providers — the HttpClient stays provider-agnostic.
    """

    def get(self) -> Optional[ProxyEndpoint]:
        """Return the current active endpoint, or None for a direct connection."""
        ...

    def report(self, endpoint: ProxyEndpoint, ok: bool) -> None:
        """Signal whether the last request via *endpoint* succeeded.

        ok=False marks a ban/block; the provider may cool-down that endpoint.
        """
        ...

    def rotate(self) -> None:
        """Advance to the next endpoint in the pool immediately."""
        ...

    def record_use(self, endpoint: ProxyEndpoint) -> None:  # pragma: no cover - optional
        """Record that *endpoint* was just used (proactive LRU + rate budget).

        Optional in the Protocol: providers that do not distribute load
        proactively (NoProxyProvider, SimulatedProxyProvider) may omit it.
        The HttpClient calls it after selection so usage-aware providers can
        keep their least-recently-used ordering and per-IP rate budget fresh.
        """
        ...

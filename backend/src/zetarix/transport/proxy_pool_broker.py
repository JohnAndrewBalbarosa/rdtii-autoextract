"""Central proxy-pool MIDDLEMAN for parallel crawlers sharing a FIXED IP pool.

Problem (product owner): when several crawlers run IN PARALLEL inside one
process (threads / asyncio), and each one rotates its OWN proxy independently,
two workers can grab the SAME egress IP at the same instant. A target site then
sees repeated hits from one IP and flags it as spam even though "we're
rotating." The fix is a single source of truth that OWNS the finite pool and
hands out coordinated, NON-COLLIDING IPs.

Design:
  * `ProxyPoolBroker` owns the master list of `ProxyEndpoint`s (stable order).
  * A HASH MAP `_index_of` (Python ``dict``, the idiomatic collision-safe hash
    realisation — we do NOT hand-roll open addressing, YAGNI) maps an IP/url to
    its index, so every "is this IP in use / has this worker used it" check is
    O(1), not a linear or radix scan over the list.
  * `_in_use` is a ``bytearray`` bitmap: 1 means "this IP is CURRENTLY leased by
    ANY worker" — the occupied flag the owner asked the masterlist to carry.
  * `_used_by` is per-worker history (worker_id -> bytearray) so a worker never
    re-uses the same IP within a rotation cycle.
  * `_last_used` drives LRU spreading (longest-idle IP wins) for even load.

Waiting / fairness (FAIR direct handoff):
  * A single ``threading.Lock`` guards ALL state.
  * When no eligible free IP exists, a worker enqueues a private waiter ticket
    (its OWN ``threading.Event`` + a one-slot result) at the BACK of a FIFO
    ``collections.deque`` and blocks on that Event.
  * On ``release``, under the lock, we scan the waiter queue FRONT->BACK for the
    FIRST waiter for whom the freed IP is ELIGIBLE (that worker has not already
    used this specific IP). If found we DIRECTLY HAND OFF the lease to exactly
    that one waiter (mark in_use under it, record usage, fill its result slot,
    set its Event, remove it from the queue). No broadcast, so there is no
    thundering herd and no lost wakeup; a front waiter that already used the
    freed IP is SKIPPED and stays queued for a future release.

This module is stdlib-only and import-clean (only depends on proxy_provider).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Iterable, Iterator, List, Optional, Union

from zetarix.transport.proxy_provider import ProxyEndpoint


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PoolExhausted(RuntimeError):
    """Raised by ``acquire`` when no eligible IP becomes available within timeout.

    Distinct from "this worker has used every IP" (which auto-resets the
    worker's rotation cycle) — this only fires when no IP for which this worker
    is eligible is handed to it before the deadline.
    """


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProxyLease:
    """Immutable receipt for one coordinated, non-colliding IP grant.

    Carries the index back so ``release`` is O(1) (no re-hash needed) and the
    caller cannot accidentally release a different endpoint than it holds.
    """

    endpoint: ProxyEndpoint
    index: int
    worker_id: int


WorkerId = int

# Sentinel: a clock-expired waiter is not in the queue yet not done -> a
# concurrent handoff is racing in; the waiter should consume it on the next loop.
_PENDING = object()


# ---------------------------------------------------------------------------
# Waiter ticket (one per blocked acquire call) — FIFO + direct handoff
# ---------------------------------------------------------------------------

@dataclass
class _Waiter:
    """A queued, blocked acquire(): its own Event + a one-slot result.

    ``lease`` is filled by a releasing thread (direct handoff) BEFORE its
    ``event`` is set; the waiter reads it after waking. ``done`` distinguishes
    a real handoff from a spurious/None wake.
    """

    worker_id: WorkerId
    event: threading.Event = field(default_factory=threading.Event)
    lease: Optional[ProxyLease] = None
    done: bool = False
    cancelled: bool = False  # set by reset(): waiter must re-attempt acquire


def _endpoint_key(endpoint: ProxyEndpoint) -> str:
    """Stable hash key for an endpoint: its full URL string.

    Two endpoints describing the same egress (same scheme/host/port/creds)
    collapse to the same key, so the pool de-dupes and the index is consistent.
    """
    return endpoint.as_url()


def _coerce_endpoint(item: Union[str, ProxyEndpoint]) -> ProxyEndpoint:
    if isinstance(item, ProxyEndpoint):
        return item
    # Lazy import to keep the dependency surface tiny / avoid cycles.
    from zetarix.transport.proxy_providers import _parse_url
    return _parse_url(item)


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

class ProxyPoolBroker:
    """Single source of truth for a fixed/finite proxy pool, shared by workers.

    Thread-safe. All mutable state is guarded by a single ``threading.Lock`` so
    invariants hold under any thread scheduling. Blocked acquirers wait on their
    OWN per-waiter ``Event`` (not a shared Condition); a releasing thread hands
    a lease directly to the first eligible FIFO waiter.
    """

    def __init__(
        self,
        proxies: Iterable[Union[str, ProxyEndpoint]],
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._clock: Callable[[], float] = clock or time.monotonic

        # Master list (stable order) + the hash index over it.
        pool: List[ProxyEndpoint] = []
        index_of: Dict[str, int] = {}
        for raw in proxies:
            ep = _coerce_endpoint(raw)
            key = _endpoint_key(ep)
            if key in index_of:
                continue  # de-dupe: same egress only occupies one slot
            index_of[key] = len(pool)
            pool.append(ep)

        self._pool: List[ProxyEndpoint] = pool
        self._index_of: Dict[str, int] = index_of
        size = len(pool)

        # Occupied flag per IP (1 == currently leased by ANY worker).
        self._in_use = bytearray(size)
        # LRU spreading: last selection time per index (-inf == never used).
        self._last_used: List[float] = [float("-inf")] * size
        # Per-worker rotation history: worker_id -> bitmap of used indices.
        self._used_by: Dict[WorkerId, bytearray] = {}

        # FIFO queue of blocked acquirers (front == longest-waiting).
        self._waiters: Deque[_Waiter] = deque()

        # Single lock guards ALL of the above.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Introspection (size, O(1) hash-index queries)
    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self._pool)

    def pending_waiters(self) -> int:
        """Test-only: number of acquirers currently blocked in the FIFO queue.

        Lets tests assert a worker is ENQUEUED without sleeping. Only counts
        waiters that have not yet been handed a lease.
        """
        with self._lock:
            return sum(1 for w in self._waiters if not w.done)

    def _index_for(self, ip: Union[str, ProxyEndpoint, int]) -> Optional[int]:
        """Resolve an IP/url/endpoint/index to its pool index in O(1)."""
        if isinstance(ip, bool):  # guard: bool is an int subclass
            return None
        if isinstance(ip, int):
            return ip if 0 <= ip < len(self._pool) else None
        key = ip if isinstance(ip, str) else _endpoint_key(ip)
        return self._index_of.get(key)

    def is_in_use(self, ip: Union[str, ProxyEndpoint, int]) -> bool:
        """O(1): is this IP currently leased by any worker?"""
        with self._lock:
            idx = self._index_for(ip)
            return idx is not None and self._in_use[idx] == 1

    def has_worker_used(
        self, worker_id: WorkerId, ip: Union[str, ProxyEndpoint, int]
    ) -> bool:
        """O(1): has *worker_id* already used this IP in its current cycle?"""
        with self._lock:
            idx = self._index_for(ip)
            if idx is None:
                return False
            used = self._used_by.get(worker_id)
            return used is not None and used[idx] == 1

    # ------------------------------------------------------------------
    # Selection / claim helpers (call with self._lock held)
    # ------------------------------------------------------------------
    def _worker_bitmap(self, worker_id: WorkerId) -> bytearray:
        used = self._used_by.get(worker_id)
        if used is None or len(used) != len(self._pool):
            used = bytearray(len(self._pool))
            self._used_by[worker_id] = used
        return used

    def _pick_index(self, worker_id: WorkerId) -> Optional[int]:
        """Pick a NON-COLLIDING, not-yet-used-by-this-worker index, LRU-first.

        Returns a concrete index, or ``-1`` when free IPs exist but this worker
        has already used all of them (caller resets the cycle), or ``None`` when
        nothing is free at all.
        """
        used = self._worker_bitmap(worker_id)
        best_idx: Optional[int] = None
        best_last = float("inf")
        any_free = False
        for idx in range(len(self._pool)):
            if self._in_use[idx]:
                continue  # collision guard: never hand out an occupied IP
            any_free = True
            if used[idx]:
                continue  # worker already rode this IP this cycle
            last = self._last_used[idx]
            if last < best_last:
                best_last = last
                best_idx = idx
        if best_idx is not None:
            return best_idx
        return -1 if any_free else None

    def _claim(self, idx: int, worker_id: WorkerId, now: float) -> ProxyLease:
        self._in_use[idx] = 1
        self._worker_bitmap(worker_id)[idx] = 1
        self._last_used[idx] = now
        return ProxyLease(
            endpoint=self._pool[idx], index=idx, worker_id=worker_id
        )

    def _eligible_index_for(self, worker_id: WorkerId) -> Optional[int]:
        """Resolve the index this worker should claim NOW, auto-resetting on full.

        Returns a free, not-already-used index (LRU), performing an auto-reset of
        the worker's used bitmap when it has used every currently-free IP.
        Returns ``None`` when nothing is free at all (caller must wait).
        """
        idx = self._pick_index(worker_id)
        if idx is None:
            return None  # nothing free -> wait
        if idx == -1:
            # Free IPs exist but this worker used them all -> fresh cycle.
            self._worker_bitmap(worker_id)[:] = bytearray(len(self._pool))
            idx = self._pick_index(worker_id)
            # After reset a free IP must exist (any_free was True above).
            assert isinstance(idx, int) and idx >= 0
        return idx

    # ------------------------------------------------------------------
    # acquire / release
    # ------------------------------------------------------------------
    def acquire(
        self,
        worker_id: Optional[WorkerId] = None,
        timeout: Optional[float] = None,
    ) -> ProxyLease:
        """Lease a coordinated egress IP that no other worker currently holds.

        Fast path: if a free IP this worker has NOT used exists, take the
        longest-idle one immediately (auto-resetting the worker's cycle if it
        has already used every free IP).

        Slow path: otherwise enqueue at the BACK of the FIFO waiter queue with a
        private Event and block until a releasing thread hands this worker an
        ELIGIBLE lease (direct handoff), or *timeout* elapses -> ``PoolExhausted``.
        """
        if worker_id is None:
            worker_id = threading.get_ident()
        if not self._pool:
            raise PoolExhausted("proxy pool is empty")

        # Loop so a reset()-cancelled waiter re-attempts with its fresh history.
        deadline: Optional[float] = None
        while True:
            with self._lock:
                idx = self._eligible_index_for(worker_id)
                if idx is not None:
                    return self._claim(idx, worker_id, self._clock())
                # No eligible free IP right now -> enqueue a FIFO waiter ticket.
                waiter = _Waiter(worker_id=worker_id)
                self._waiters.append(waiter)
                if timeout is not None and deadline is None:
                    deadline = self._clock() + timeout

            # Block OUTSIDE the lock on this waiter's own Event. A releasing
            # thread fills waiter.lease + sets waiter.done before the Event.
            lease = self._wait_for_handoff(waiter, timeout, deadline)
            if lease is not None:
                return lease
            # waiter.cancelled (reset) -> retry the whole acquire from scratch.

    def _wait_for_handoff(
        self,
        waiter: _Waiter,
        timeout: Optional[float],
        deadline: Optional[float],
    ) -> Optional[ProxyLease]:
        """Block on the waiter's Event until handed a lease or the deadline.

        Returns the handed lease, ``None`` if the waiter was cancelled by
        ``reset`` (caller re-attempts), or raises ``PoolExhausted`` on timeout.

        ``deadline`` is in CLOCK units (injected clock); the OS-level Event wait
        uses a wall-clock-derived remaining only as a wakeup hint — eligibility
        and timeout are re-decided under the lock against the injected clock, so
        a fake clock that never advances yields a prompt ``PoolExhausted``.
        """
        while True:
            if timeout is None:
                woke = waiter.event.wait()
            else:
                remaining_clock = deadline - self._clock()  # type: ignore[operator]
                if remaining_clock <= 0:
                    # Deadline already passed per the (possibly fake) clock.
                    outcome = self._resolve_timeout(waiter, timeout)
                    if outcome is not _PENDING:
                        return outcome  # lease, None (cancelled), or raises
                    woke = True  # a handoff raced in -> consume it below
                else:
                    woke = waiter.event.wait(timeout=remaining_clock)

            with self._lock:
                if waiter.done:
                    assert waiter.lease is not None
                    return waiter.lease
                if waiter.cancelled:
                    return None  # reset() pulled us -> caller re-attempts
                if not woke:
                    # Timed out at the OS level; re-check the injected deadline.
                    if deadline is not None and self._clock() >= deadline:
                        if self._remove_waiter(waiter):
                            raise PoolExhausted(
                                "no eligible proxy became available; "
                                f"timed out after {timeout}s"
                            )
                        # Raced with a handoff -> loop reads waiter.done above.
                # Spurious / not-yet-handed wake: clear and loop to wait again.
                waiter.event.clear()

    def _resolve_timeout(
        self, waiter: _Waiter, timeout: Optional[float]
    ) -> Optional[ProxyLease]:
        """Under the lock, settle a clock-expired waiter.

        Returns ``_PENDING`` if a handoff raced in (caller consumes it),
        the lease if already handed, ``None`` if cancelled by reset, or raises
        ``PoolExhausted`` after removing the still-pending waiter.
        """
        with self._lock:
            if waiter.done:
                assert waiter.lease is not None
                return waiter.lease
            if waiter.cancelled:
                return None
            if self._remove_waiter(waiter):
                raise PoolExhausted(
                    "no eligible proxy became available; "
                    f"timed out after {timeout}s"
                )
            return _PENDING  # not in queue but not done -> a handoff is racing

    def _remove_waiter(self, waiter: _Waiter) -> bool:
        """Remove *waiter* from the queue if still present (call under lock)."""
        try:
            self._waiters.remove(waiter)
            return True
        except ValueError:
            return False

    def release(
        self,
        lease_or_worker: Union[ProxyLease, WorkerId, None] = None,
        endpoint: Optional[ProxyEndpoint] = None,
    ) -> None:
        """Free a leased IP and DIRECTLY HAND it to the first eligible waiter.

        Two call shapes:
          * ``release(lease)`` — preferred, O(1) via the lease's index.
          * ``release(worker_id, endpoint)`` — resolve index via the hash map.

        On release we scan the FIFO waiter queue FRONT->BACK for the first
        waiter for whom this freed IP is eligible (has not already used it). If
        found, hand the lease to exactly that waiter (it stays in_use, never
        flips to free). A front waiter that already used this IP is SKIPPED and
        stays queued. If no queued waiter is eligible, the IP is left free.

        Releasing an IP that is not in use is a harmless no-op (idempotent).
        """
        with self._lock:
            idx: Optional[int]
            if isinstance(lease_or_worker, ProxyLease):
                idx = lease_or_worker.index
            elif endpoint is not None:
                idx = self._index_for(endpoint)
            else:
                raise TypeError(
                    "release requires a ProxyLease, or (worker_id, endpoint)"
                )
            if idx is None or not (0 <= idx < len(self._pool)):
                return
            if not self._in_use[idx]:
                return  # already free -> nothing to hand off

            # Try to DIRECTLY HAND this still-in_use IP to a FIFO waiter.
            handed = self._handoff_locked(idx)
            if not handed:
                # No eligible queued waiter -> the IP genuinely returns to free.
                self._in_use[idx] = 0

    def _handoff_locked(self, idx: int) -> bool:
        """Hand the in_use IP *idx* to the first eligible FIFO waiter.

        Call with the lock held and ``_in_use[idx] == 1``. Scans front->back;
        the first waiter that has NOT used this IP gets a direct handoff (usage
        recorded under ITS worker_id, lease placed in its slot, Event set,
        removed from queue). Returns True iff a handoff happened.
        """
        for waiter in self._waiters:
            used = self._worker_bitmap(waiter.worker_id)
            if used[idx]:
                continue  # this waiter already rode this IP -> skip, keep queued
            # Direct handoff: re-attribute the still-in_use slot to this worker.
            now = self._clock()
            used[idx] = 1
            self._last_used[idx] = now
            # _in_use[idx] stays 1 (never flips to free between hands).
            waiter.lease = ProxyLease(
                endpoint=self._pool[idx], index=idx, worker_id=waiter.worker_id
            )
            waiter.done = True
            self._waiters.remove(waiter)
            waiter.event.set()
            return True
        return False

    # ------------------------------------------------------------------
    # Reset (explicit + the auto-reset is folded into acquire/handoff)
    # ------------------------------------------------------------------
    def reset(self, worker_id: Optional[WorkerId] = None) -> None:
        """Clear *worker_id*'s used history — "fresh, like new" full rotation.

        Also removes the worker from the waiter queue if it is currently blocked
        (its acquire() will then time out or re-decide on its own). Auto-reset on
        a full used-bitmap is handled inside ``acquire``/handoff, so this is the
        EXPLICIT counterpart for "this worker finished a job, recycle it."
        """
        if worker_id is None:
            worker_id = threading.get_ident()
        with self._lock:
            used = self._used_by.get(worker_id)
            if used is not None:
                used[:] = bytearray(len(self._pool))
            # Drop any pending waiter ticket(s) for this worker so its blocked
            # acquire() re-attempts from scratch with the now-fresh history.
            stale = [w for w in self._waiters if w.worker_id == worker_id and not w.done]
            for w in stale:
                w.cancelled = True
                self._waiters.remove(w)
                w.event.set()  # wake it so it re-decides eligibility

    # Alias requested by the product owner.
    def complete(self, worker_id: Optional[WorkerId] = None) -> None:
        """Alias for :meth:`reset` — "this worker completed its job."""
        self.reset(worker_id)

    # ------------------------------------------------------------------
    # Context manager ergonomics
    # ------------------------------------------------------------------
    @contextmanager
    def lease(
        self,
        worker_id: Optional[WorkerId] = None,
        timeout: Optional[float] = None,
    ) -> Iterator[ProxyEndpoint]:
        """``with broker.lease() as ep:`` — acquire on enter, release on exit."""
        acquired = self.acquire(worker_id=worker_id, timeout=timeout)
        try:
            yield acquired.endpoint
        finally:
            self.release(acquired)

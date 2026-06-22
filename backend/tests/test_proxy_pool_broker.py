"""Tests for the ProxyPoolBroker middleman + BrokeredProxyProvider integration.

Deterministic units use an injected `_FakeClock` (no wall-clock dependency).
The threaded invariant test uses real threads but asserts an INVARIANT that must
hold under ANY scheduling: no pool index is ever held by two leases at once.
"""
from __future__ import annotations

import threading
import time
from typing import List

import pytest

from adapters.botting.l4_transport.proxy_provider import ProxyEndpoint
from adapters.botting.l4_transport.proxy_pool_broker import (
    PoolExhausted,
    ProxyLease,
    ProxyPoolBroker,
)
from adapters.botting.l4_transport.proxy_providers import (
    BrokeredProxyProvider,
    proxy_provider_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeClock:
    """Deterministic injectable monotonic clock (no wall-clock dependency)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


def _pool(n: int) -> List[str]:
    return [f"http://p{i}.example.com:80" for i in range(n)]


def _host(i: int) -> str:
    return f"p{i}.example.com"


# ---------------------------------------------------------------------------
# Construction + hash-index correctness
# ---------------------------------------------------------------------------

class TestConstructionAndIndex:

    def test_pool_preserves_order_and_builds_hash_index(self):
        broker = ProxyPoolBroker(_pool(3))
        assert broker.size == 3
        # _index_of maps each url -> its stable list position (O(1) lookups).
        for i in range(3):
            url = f"http://{_host(i)}:80"
            assert broker._index_of[url] == i
            assert broker._pool[i].host == _host(i)

    def test_duplicate_endpoints_are_deduped(self):
        broker = ProxyPoolBroker(_pool(2) + _pool(2))  # two dupes
        assert broker.size == 2

    def test_accepts_endpoint_objects_and_strings(self):
        ep = ProxyEndpoint(scheme="http", host="x.example.com", port=8080)
        broker = ProxyPoolBroker([ep, "http://y.example.com:80"])
        assert broker.size == 2
        assert broker.is_in_use(ep) is False
        assert broker.is_in_use("http://y.example.com:80") is False

    def test_is_in_use_unknown_ip_is_false(self):
        broker = ProxyPoolBroker(_pool(1))
        assert broker.is_in_use("http://nope.example.com:80") is False

    def test_index_query_by_int_index(self):
        broker = ProxyPoolBroker(_pool(2))
        lease = broker.acquire(worker_id=1)
        # is_in_use accepts a raw index too.
        assert broker.is_in_use(lease.index) is True


# ---------------------------------------------------------------------------
# acquire: collision avoidance + LRU + worker rotation
# ---------------------------------------------------------------------------

class TestAcquireSelection:

    def test_acquire_marks_in_use_and_skips_it_for_others(self):
        broker = ProxyPoolBroker(_pool(2))
        a = broker.acquire(worker_id=1)
        assert broker.is_in_use(a.endpoint) is True
        # A DIFFERENT worker must get the OTHER (not in_use) index.
        b = broker.acquire(worker_id=2)
        assert b.index != a.index
        assert broker.is_in_use(b.endpoint) is True

    def test_acquire_skips_ip_already_used_by_same_worker(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(3), clock=clock)
        seen = set()
        for _ in range(3):
            lease = broker.acquire(worker_id=7)
            seen.add(lease.index)
            broker.release(lease)        # free it, but worker recorded usage
            clock.advance(1)
        # Same worker rotated through ALL three distinct IPs before repeating.
        assert seen == {0, 1, 2}
        assert broker.has_worker_used(7, lease.endpoint) is True

    def test_lru_picks_longest_idle(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(3), clock=clock)
        # Use+release each in order 0,1,2 with advancing clock.
        for _ in range(3):
            lease = broker.acquire(worker_id=1)
            broker.release(lease)
            clock.advance(1)
        # Worker 1 used all three -> next acquire resets its cycle and must
        # pick the LONGEST-IDLE index, which is index 0 (used earliest).
        nxt = broker.acquire(worker_id=1)
        assert nxt.index == 0


# ---------------------------------------------------------------------------
# release + condition wakeups
# ---------------------------------------------------------------------------

class TestRelease:

    def test_release_frees_ip_for_another_worker(self):
        broker = ProxyPoolBroker(_pool(1))
        a = broker.acquire(worker_id=1)
        assert broker.is_in_use(a.endpoint) is True
        broker.release(a)
        assert broker.is_in_use(a.endpoint) is False
        # Now a different worker can take the single IP.
        b = broker.acquire(worker_id=2)
        assert b.index == a.index

    def test_release_by_worker_and_endpoint(self):
        broker = ProxyPoolBroker(_pool(2))
        a = broker.acquire(worker_id=1)
        broker.release(1, a.endpoint)
        assert broker.is_in_use(a.endpoint) is False

    def test_release_is_idempotent(self):
        broker = ProxyPoolBroker(_pool(1))
        a = broker.acquire(worker_id=1)
        broker.release(a)
        broker.release(a)  # second release is a harmless no-op
        assert broker.is_in_use(a.endpoint) is False

    def test_release_requires_lease_or_worker_endpoint(self):
        broker = ProxyPoolBroker(_pool(1))
        with pytest.raises(TypeError):
            broker.release()


# ---------------------------------------------------------------------------
# context manager ergonomics
# ---------------------------------------------------------------------------

class TestContextManager:

    def test_lease_context_manager_auto_releases(self):
        broker = ProxyPoolBroker(_pool(1))
        with broker.lease(worker_id=1) as ep:
            assert isinstance(ep, ProxyEndpoint)
            assert broker.is_in_use(ep) is True
        # On exit the IP is back in the pool.
        assert broker.is_in_use(ep) is False

    def test_lease_releases_on_exception(self):
        broker = ProxyPoolBroker(_pool(1))
        captured = {}
        with pytest.raises(ValueError):
            with broker.lease(worker_id=1) as ep:
                captured["ep"] = ep
                raise ValueError("boom")
        assert broker.is_in_use(captured["ep"]) is False


# ---------------------------------------------------------------------------
# worker-exhaustion cycle reset
# ---------------------------------------------------------------------------

class TestWorkerExhaustionCycle:

    def test_worker_used_set_resets_after_exhausting_distinct_ips(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(2), clock=clock)
        # Worker uses both IPs (releasing each so they're free again).
        first = broker.acquire(worker_id=9); broker.release(first); clock.advance(1)
        second = broker.acquire(worker_id=9); broker.release(second); clock.advance(1)
        assert {first.index, second.index} == {0, 1}
        assert broker.has_worker_used(9, first.endpoint) is True
        # Worker has used every free IP -> cycle resets, has_worker_used clears.
        third = broker.acquire(worker_id=9)
        assert third.index in {0, 1}
        # After the reset the OTHER index is no longer marked used.
        other = 1 - third.index
        assert broker.has_worker_used(9, broker._pool[other]) is False


# ---------------------------------------------------------------------------
# contention timeout
# ---------------------------------------------------------------------------

class TestContentionTimeout:

    def test_timeout_raises_pool_exhausted_when_all_in_use(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(1), clock=clock)
        broker.acquire(worker_id=1)  # the only IP is now in use, never released

        # Worker 2 cannot get anything; with a fake clock the deadline is
        # already passed on the first re-check, so it raises promptly.
        with pytest.raises(PoolExhausted):
            broker.acquire(worker_id=2, timeout=0.0)

    def test_empty_pool_raises_pool_exhausted(self):
        broker = ProxyPoolBroker([])
        with pytest.raises(PoolExhausted):
            broker.acquire(worker_id=1, timeout=0.0)

    def test_waiter_wakes_on_release(self):
        """A real waiter blocks, then proceeds once the holder releases."""
        broker = ProxyPoolBroker(_pool(1))  # real monotonic clock here
        held = broker.acquire(worker_id=1)

        got: List[ProxyLease] = []
        started = threading.Event()

        def waiter():
            started.set()
            got.append(broker.acquire(worker_id=2, timeout=5.0))

        t = threading.Thread(target=waiter)
        t.start()
        started.wait(timeout=2.0)
        # Give the waiter a moment to actually block on the condition, then
        # release; correctness does not depend on exact timing.
        broker.release(held)
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert len(got) == 1
        assert got[0].index == held.index


# ---------------------------------------------------------------------------
# THREADED invariant: no index is ever held by two leases at once
# ---------------------------------------------------------------------------

class TestThreadedInvariant:

    def test_no_two_workers_ever_hold_the_same_ip(self):
        pool_size = 4
        n_workers = 8          # more workers than IPs -> real contention
        iters = 200
        broker = ProxyPoolBroker(_pool(pool_size))  # real clock

        # Concurrent-holders tracker, guarded by its own lock. The INVARIANT:
        # at no instant is any index held by more than one worker.
        holders = [0] * pool_size
        holders_lock = threading.Lock()
        violations: List[str] = []
        barrier = threading.Barrier(n_workers)

        def worker(wid: int) -> None:
            barrier.wait()  # maximise overlap / contention
            for _ in range(iters):
                lease = broker.acquire(worker_id=wid, timeout=10.0)
                idx = lease.index
                with holders_lock:
                    holders[idx] += 1
                    if holders[idx] != 1:
                        violations.append(
                            f"index {idx} held by {holders[idx]} workers"
                        )
                    # Broker invariant: an acquired index must read as in_use.
                    if not broker.is_in_use(idx):
                        violations.append(f"index {idx} acquired but not in_use")
                # tiny hold under no lock to widen the race window
                with holders_lock:
                    holders[idx] -= 1
                broker.release(lease)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(n_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert all(not t.is_alive() for t in threads), "threads deadlocked"
        assert violations == [], f"invariant violated: {violations[:5]}"
        # Pool fully drained at the end (every lease released).
        assert all(broker._in_use[i] == 0 for i in range(pool_size))


# ---------------------------------------------------------------------------
# BrokeredProxyProvider integration + factory switch
# ---------------------------------------------------------------------------

class TestBrokeredProxyProvider:

    def test_get_releases_previous_and_rotates(self):
        broker = ProxyPoolBroker(_pool(3))
        provider = BrokeredProxyProvider(broker)
        # Same worker (thread) -> consecutive get() calls rotate distinct IPs,
        # and the previous lease is released so at most one is in_use per worker.
        first = provider.get()
        assert first is not None
        in_use_after_first = sum(broker._in_use)
        second = provider.get()
        assert second is not None
        assert second.host != first.host
        # Previous lease released -> still exactly one IP held by this worker.
        assert sum(broker._in_use) == in_use_after_first == 1

    def test_two_threads_never_collide_via_provider(self):
        broker = ProxyPoolBroker(_pool(2))
        provider = BrokeredProxyProvider(broker)
        results = {}

        def grab(name: str) -> None:
            ep = provider.get()
            results[name] = ep.host if ep else None

        t1 = threading.Thread(target=grab, args=("a",))
        t1.start(); t1.join()
        t2 = threading.Thread(target=grab, args=("b",))
        t2.start(); t2.join()
        # Distinct threads (workers) hold distinct IPs.
        assert results["a"] != results["b"]

    def test_release_returns_ip_to_pool(self):
        broker = ProxyPoolBroker(_pool(1))
        provider = BrokeredProxyProvider(broker)
        ep = provider.get()
        assert ep is not None
        assert sum(broker._in_use) == 1
        provider.release()
        assert sum(broker._in_use) == 0

    def test_report_cools_bad_ip_so_get_skips_it(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(2), clock=clock)
        provider = BrokeredProxyProvider(broker, cooldown=300, clock=clock)
        bad = provider.get()
        provider.report(bad, ok=False)
        # Next get() (same worker) must skip the cooled IP.
        nxt = provider.get()
        assert nxt is not None
        assert nxt.host != bad.host

    def test_get_returns_none_when_pool_empty(self):
        broker = ProxyPoolBroker([])
        provider = BrokeredProxyProvider(broker, acquire_timeout=0.0)
        assert provider.get() is None

    def test_factory_brokered_mode(self):
        p = proxy_provider_from_config({
            "PROXY_MODE": "brokered",
            "PROXY_LIST": "http://a.example.com:80,http://b.example.com:80",
        })
        assert isinstance(p, BrokeredProxyProvider)
        ep = p.get()
        assert ep is not None
        assert ep.host in {"a.example.com", "b.example.com"}

    def test_factory_coordinated_flag(self):
        p = proxy_provider_from_config({
            "PROXY_COORDINATED": "1",
            "PROXY_LIST": "http://a.example.com:80",
        })
        assert isinstance(p, BrokeredProxyProvider)

    def test_provider_reset_lets_worker_reuse_a_used_ip(self):
        # Single-IP pool: re-acquiring the SAME host is only possible because
        # reset() cleared the worker's used history (otherwise the worker would
        # be "out of distinct IPs" and only an auto-reset cycle would allow it).
        broker = ProxyPoolBroker(_pool(1))
        provider = BrokeredProxyProvider(broker)
        first = provider.get()
        assert first is not None
        wid = threading.get_ident()
        assert broker.has_worker_used(wid, first) is True
        # reset() releases the lease AND clears history -> truly fresh.
        provider.reset()
        assert sum(broker._in_use) == 0
        assert broker.has_worker_used(wid, first) is False
        again = provider.get()
        assert again is not None
        assert again.host == first.host  # same single IP, reusable post-reset


# ---------------------------------------------------------------------------
# pending_waiters introspection (no sleeping in tests)
# ---------------------------------------------------------------------------

def _spawn_blocked_acquire(broker, worker_id, timeout, out):
    """Start a thread that blocks in acquire(); return (thread, started_event).

    Spins (no sleep) on broker.pending_waiters() at the call site to know when
    the thread is actually enqueued.
    """
    started = threading.Event()

    def run():
        started.set()
        try:
            out.append(broker.acquire(worker_id=worker_id, timeout=timeout))
        except PoolExhausted as exc:  # pragma: no cover - only on intended timeout
            out.append(exc)

    t = threading.Thread(target=run)
    t.start()
    started.wait(timeout=2.0)
    return t


def _wait_until(predicate, timeout=3.0):
    """Busy-wait (tiny yields) on a predicate without depending on sleeps."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.001)  # yield the GIL; not a correctness-bearing sleep
    return predicate()


class TestDirectHandoffEligibility:

    def test_waiter_handed_a_proxy_it_has_not_used(self):
        """pool=2; A holds both; B blocks; releasing a B-UNUSED proxy unblocks B."""
        broker = ProxyPoolBroker(_pool(2))
        a0 = broker.acquire(worker_id=1)
        a1 = broker.acquire(worker_id=1)
        # B has used nothing yet -> any release is eligible for it.
        out: List = []
        t = _spawn_blocked_acquire(broker, worker_id=2, timeout=5.0, out=out)
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        assert broker.pending_waiters() == 1
        # Release a0 -> direct handoff to B (B never used a0.index).
        broker.release(a0)
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert len(out) == 1 and isinstance(out[0], ProxyLease)
        assert out[0].index == a0.index
        assert broker.is_in_use(a0.index) is True  # stayed in_use across handoff
        broker.release(a1)

    def test_waiter_skipped_when_freed_proxy_already_used(self):
        """B blocks; releasing a proxy B ALREADY used keeps B blocked; an unused one frees it."""
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(2), clock=clock)
        # B uses ONE index first, then releases it; record which one (B's history
        # now marks `b_used`; the other index `b_unused` is still fresh for B).
        b_first = broker.acquire(worker_id=2)
        b_used = b_first.index
        b_unused = 1 - b_used
        broker.release(b_first)
        clock.advance(1)
        # A now grabs BOTH indices so B will block on its next acquire.
        x = broker.acquire(worker_id=1)
        y = broker.acquire(worker_id=1)
        assert {x.index, y.index} == {0, 1}
        lease_used = x if x.index == b_used else y      # the IP B already rode
        lease_unused = x if x.index == b_unused else y  # the IP B has NOT ridden
        out: List = []
        t = _spawn_blocked_acquire(broker, worker_id=2, timeout=5.0, out=out)
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        # Release the index B ALREADY used -> B must NOT be handed it.
        broker.release(lease_used)
        # B stays blocked; that index is left genuinely free (no eligible waiter).
        assert _wait_until(lambda: broker.is_in_use(b_used) is False)
        assert broker.pending_waiters() == 1, "B wrongly handed an already-used IP"
        assert out == []
        # Now release the index B has NOT used -> direct handoff unblocks B.
        broker.release(lease_unused)
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert len(out) == 1 and isinstance(out[0], ProxyLease)
        assert out[0].index == b_unused
        broker.release(out[0])


class TestFifoFairness:

    def test_earlier_queued_waiter_gets_the_released_proxy(self):
        """Two eligible waiters -> the EARLIER-queued one wins the handoff."""
        broker = ProxyPoolBroker(_pool(1))
        held = broker.acquire(worker_id=1)
        out_b: List = []
        out_c: List = []
        # B enqueues first, then C — strict FIFO order.
        tb = _spawn_blocked_acquire(broker, worker_id=2, timeout=5.0, out=out_b)
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        tc = _spawn_blocked_acquire(broker, worker_id=3, timeout=5.0, out=out_c)
        assert _wait_until(lambda: broker.pending_waiters() == 2)
        # One release -> only the FRONT waiter (B) is served.
        broker.release(held)
        tb.join(timeout=5.0)
        assert not tb.is_alive()
        assert len(out_b) == 1 and isinstance(out_b[0], ProxyLease)
        # C is still waiting (only one IP was freed).
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        assert out_c == []
        # Free B's IP -> now C is served (FIFO, C was next).
        broker.release(out_b[0])
        tc.join(timeout=5.0)
        assert not tc.is_alive()
        assert len(out_c) == 1 and isinstance(out_c[0], ProxyLease)
        broker.release(out_c[0])


class TestResetSemantics:

    def test_explicit_reset_clears_usage(self):
        # Single-IP pool: re-acquiring the SAME index after release is only
        # possible because reset() cleared the worker's used history.
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(1), clock=clock)
        a = broker.acquire(worker_id=5)
        broker.release(a)
        assert broker.has_worker_used(5, a.endpoint) is True
        broker.reset(5)
        assert broker.has_worker_used(5, a.endpoint) is False
        # After reset the worker can re-acquire the SAME (only) index it just used.
        clock.advance(1)
        again = broker.acquire(worker_id=5)
        assert again.index == a.index

    def test_complete_alias_resets(self):
        broker = ProxyPoolBroker(_pool(1))
        a = broker.acquire(worker_id=5)
        broker.release(a)
        broker.complete(5)
        assert broker.has_worker_used(5, a.endpoint) is False

    def test_auto_reset_when_used_bitmap_fills(self):
        clock = _FakeClock()
        broker = ProxyPoolBroker(_pool(2), clock=clock)
        i0 = broker.acquire(worker_id=8); broker.release(i0); clock.advance(1)
        i1 = broker.acquire(worker_id=8); broker.release(i1); clock.advance(1)
        assert {i0.index, i1.index} == {0, 1}  # used the whole pool
        # Bitmap is now full -> the next acquire AUTO-resets and starts fresh.
        i2 = broker.acquire(worker_id=8)
        assert i2.index in {0, 1}
        # The other index is no longer marked used post auto-reset.
        other = 1 - i2.index
        assert broker.has_worker_used(8, broker._pool[other]) is False

    def test_reset_unblocks_a_waiting_worker_to_retry(self):
        """reset() on a blocked worker pulls it from the queue to re-attempt."""
        broker = ProxyPoolBroker(_pool(1))
        held = broker.acquire(worker_id=1)
        out: List = []
        t = _spawn_blocked_acquire(broker, worker_id=2, timeout=5.0, out=out)
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        # reset worker 2 -> it leaves the queue, re-attempts, still nothing free,
        # so it re-enqueues. Net: it is back to pending (liveness preserved).
        broker.reset(2)
        assert _wait_until(lambda: broker.pending_waiters() == 1)
        # Releasing the only IP still hands it off correctly.
        broker.release(held)
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert len(out) == 1 and isinstance(out[0], ProxyLease)
        broker.release(out[0])

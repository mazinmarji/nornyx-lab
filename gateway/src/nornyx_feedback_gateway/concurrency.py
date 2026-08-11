"""Serialisation and retention primitives for a service handling concurrent requests.

Two problems live here, both of which look like nothing until the service has
more than one request in flight at a time.

**Read-decide-write is not atomic.** Synchronisation looks up a session, decides
whether to create or update, and then writes. Two requests carrying the same
previously unseen session can both complete the lookup before either writes, and
both then create — producing exactly the duplicate issue the whole idempotency
model exists to prevent. ``KeyedLocks`` closes that by serialising per session.

**Per-client state accumulates.** A rate limiter keyed by client address grows
one entry per distinct address, and expiring only the bucket currently being
touched means an address that never returns is never cleaned up. Over a long
uptime that is both unbounded memory and a retained record of who connected —
which contradicts the claim that client addresses are held only transiently.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class KeyedLocks:
    """One mutex per key, created on demand and discarded when idle.

    Reference-counted rather than striped. Striping is simpler but makes
    unrelated keys contend by hash collision, and "these two sessions are
    independent" is a property worth keeping exactly true rather than usually
    true. The registry is bounded by the number of *concurrently held* keys, not
    by the number of keys ever seen, because the last holder removes the entry.
    """

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._locks: dict[str, tuple[threading.Lock, int]] = {}

    @contextmanager
    def hold(self, key: str) -> Iterator[None]:
        with self._registry_lock:
            lock, holders = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, holders + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._registry_lock:
                existing, count = self._locks[key]
                if count <= 1:
                    del self._locks[key]
                else:
                    self._locks[key] = (existing, count - 1)

    def tracked_keys(self) -> int:
        """How many keys currently hold registry space. Exposed for tests."""

        with self._registry_lock:
            return len(self._locks)


class RateLimiter:
    """A fixed-window counter that forgets clients, bounded and thread-safe.

    Proportionate, not comprehensive. It exists so one misbehaving client cannot
    trivially exhaust the GitHub rate budget; it is not a substitute for the
    reverse proxy or cloud edge controls the deployment guide asks for, and it
    neither survives a restart nor coordinates across replicas.

    Three properties the naive version did not have:

    * **Thread safety.** Uvicorn runs the endpoint in a worker thread, so two
      requests really do mutate this concurrently.
    * **Global expiry.** Stale buckets are swept on a schedule, not only when
      the same client happens to return. An address seen once and never again
      disappears on the next sweep.
    * **A hard bound.** Past ``max_clients`` the least recently active bucket is
      evicted, so memory cannot grow with the number of distinct addresses. The
      eviction order is deterministic and testable rather than incidental.

    The client address is a bucket key and nothing else. It is never written to
    the database, never logged, and never returned.
    """

    def __init__(
        self,
        *,
        per_minute: int,
        max_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
        sweep_interval_seconds: float = 60.0,
    ) -> None:
        self.per_minute = per_minute
        self.max_clients = max_clients
        self.sweep_interval_seconds = sweep_interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        # Ordered by recency of activity, so eviction is "oldest first" rather
        # than "whatever the dict happened to yield".
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._last_sweep = clock()

    # ------------------------------------------------------------------ policy
    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            # A limit of zero disables limiting rather than refusing everyone.
            # A misconfiguration must not become a denial of the legitimate path.
            return True
        now = self._clock()
        with self._lock:
            self._sweep_locked(now)
            window = self._hits.get(key)
            if window is None:
                window = deque()
                self._hits[key] = window
            self._hits.move_to_end(key)
            self._expire(window, now)
            if len(window) >= self.per_minute:
                return False
            window.append(now)
            self._evict_locked()
            return True

    # ----------------------------------------------------------------- retention
    @staticmethod
    def _expire(window: deque[float], now: float) -> None:
        while window and now - window[0] >= 60.0:
            window.popleft()

    def _sweep_locked(self, now: float) -> None:
        """Drop every bucket with nothing left in its window.

        Runs at most once per sweep interval so an ordinary request pays
        nothing; the cost lands on whichever request happens to cross the
        boundary.
        """

        if now - self._last_sweep < self.sweep_interval_seconds:
            return
        self._last_sweep = now
        for key in [key for key, window in self._hits.items() if not self._live(window, now)]:
            del self._hits[key]

    @staticmethod
    def _live(window: deque[float], now: float) -> bool:
        return bool(window) and now - window[-1] < 60.0

    def _evict_locked(self) -> None:
        while len(self._hits) > self.max_clients:
            # ``OrderedDict`` pops in insertion/activity order, so this is the
            # least recently active client every time.
            self._hits.popitem(last=False)

    def sweep(self) -> None:
        """Force a sweep. Exists so tests do not have to guess the schedule."""

        now = self._clock()
        with self._lock:
            self._last_sweep = now - self.sweep_interval_seconds
            self._sweep_locked(now)

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._hits)


__all__ = ["KeyedLocks", "RateLimiter"]

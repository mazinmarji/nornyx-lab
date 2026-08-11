"""The rate limiter must forget clients, stay bounded, and survive concurrency.

Three defects in the original, all invisible at one request per test:

* **It only expired the bucket being touched.** A client that connected once and
  never returned kept its entry for the process lifetime. That is unbounded
  memory, and — more importantly — it contradicts the documented claim that
  client addresses are held only transiently.
* **The cleanup pass ran only when the map exceeded a threshold and only removed
  buckets that were already empty**, which the expiry above rarely produced.
* **It was not thread-safe.** Uvicorn dispatches the endpoint on a worker
  thread, so two requests genuinely mutate the same map at the same time.

The clock is injected throughout, so retention is asserted deterministically
rather than by sleeping.
"""

from __future__ import annotations

import threading

from nornyx_feedback_gateway.concurrency import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ------------------------------------------------------------------ retention
def test_a_client_that_never_returns_is_forgotten() -> None:
    """The exact defect: one-off addresses accumulating forever."""

    clock = Clock()
    limiter = RateLimiter(per_minute=5, clock=clock)

    for index in range(5_000):
        assert limiter.allow(f"198.51.100.{index}") is True
    assert limiter.tracked_clients() == 5_000

    # None of them ever comes back.
    clock.advance(61.0)
    limiter.sweep()

    assert limiter.tracked_clients() == 0, (
        "addresses seen once were retained after their window expired"
    )


def test_the_sweep_runs_on_its_own_without_an_explicit_call() -> None:
    """Retention must not depend on a test helper being invoked."""

    clock = Clock()
    limiter = RateLimiter(per_minute=5, clock=clock, sweep_interval_seconds=60.0)
    for index in range(1_000):
        limiter.allow(f"203.0.113.{index}")
    assert limiter.tracked_clients() == 1_000

    clock.advance(61.0)
    # An ordinary request from anybody crosses the sweep boundary.
    limiter.allow("192.0.2.1")

    assert limiter.tracked_clients() == 1


def test_an_active_client_is_not_swept_away() -> None:
    """Positive control: forgetting must not forget the clients still here."""

    clock = Clock()
    limiter = RateLimiter(per_minute=5, clock=clock)
    limiter.allow("stale")
    clock.advance(50.0)
    limiter.allow("active")

    clock.advance(15.0)  # stale is now 65s old, active is 15s old
    limiter.sweep()

    assert limiter.tracked_clients() == 1
    assert limiter.allow("active") is True


# --------------------------------------------------------------------- bounds
def test_the_bucket_count_is_hard_bounded() -> None:
    clock = Clock()
    limiter = RateLimiter(per_minute=5, max_clients=100, clock=clock)

    for index in range(10_000):
        limiter.allow(f"client-{index}")

    assert limiter.tracked_clients() <= 100


def test_eviction_removes_the_least_recently_active_client_first() -> None:
    """Deterministic, not "whatever the dict yielded"."""

    clock = Clock()
    limiter = RateLimiter(per_minute=5, max_clients=3, clock=clock)

    for key in ("a", "b", "c"):
        limiter.allow(key)
        clock.advance(1.0)
    # Touch "a" so it is no longer the oldest by activity.
    limiter.allow("a")
    clock.advance(1.0)

    limiter.allow("d")  # forces one eviction

    assert limiter.tracked_clients() == 3
    # "b" was the least recently active and is the one that went.
    assert limiter._hits.keys() >= {"a", "c", "d"}
    assert "b" not in limiter._hits


def test_eviction_does_not_grant_an_evicted_client_extra_allowance_for_others() -> None:
    """Eviction is a memory bound, not a way to reset someone else's counter."""

    clock = Clock()
    limiter = RateLimiter(per_minute=2, max_clients=2, clock=clock)

    assert limiter.allow("victim") is True
    assert limiter.allow("victim") is True
    assert limiter.allow("victim") is False

    limiter.allow("other")
    limiter.allow("pusher")  # evicts the least recently active

    # The limit for a client still tracked is unchanged.
    assert limiter.allow("pusher") is True


# --------------------------------------------------------------------- policy
def test_ordinary_per_client_limiting_still_works() -> None:
    clock = Clock()
    limiter = RateLimiter(per_minute=3, clock=clock)

    assert [limiter.allow("one") for _ in range(5)] == [True, True, True, False, False]
    # A different client has its own budget.
    assert limiter.allow("two") is True


def test_the_window_rolls_forward() -> None:
    clock = Clock()
    limiter = RateLimiter(per_minute=2, clock=clock)

    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False

    clock.advance(61.0)
    assert limiter.allow("a") is True


def test_a_zero_limit_disables_limiting_rather_than_refusing_everyone() -> None:
    limiter = RateLimiter(per_minute=0, clock=Clock())
    assert all(limiter.allow("anyone") for _ in range(100))
    assert limiter.tracked_clients() == 0


# ---------------------------------------------------------------- concurrency
def test_concurrent_callers_do_not_corrupt_the_counters() -> None:
    """Two threads really do hit this at once under Uvicorn."""

    limiter = RateLimiter(per_minute=1_000_000, max_clients=10_000)
    errors: list[BaseException] = []

    def hammer(worker: int) -> None:
        try:
            for index in range(500):
                limiter.allow(f"client-{index % 50}")
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(worker,)) for worker in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert not any(thread.is_alive() for thread in threads)
    assert limiter.tracked_clients() == 50


def test_the_limit_is_enforced_exactly_once_under_concurrency() -> None:
    """The counter must not over-admit because two threads read it together."""

    limiter = RateLimiter(per_minute=100, max_clients=10)
    admitted: list[bool] = []
    guard = threading.Lock()
    start = threading.Barrier(10)

    def attempt() -> None:
        start.wait(timeout=10)
        for _ in range(20):
            allowed = limiter.allow("single-client")
            with guard:
                admitted.append(allowed)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sum(admitted) == 100, f"admitted {sum(admitted)} of a 100-per-minute budget"
    assert len(admitted) == 200


def test_no_client_address_is_retained_beyond_its_window() -> None:
    """The privacy claim, checked as a property of the limiter's state."""

    clock = Clock()
    limiter = RateLimiter(per_minute=5, clock=clock)
    limiter.allow("198.51.100.42")
    assert "198.51.100.42" in limiter._hits

    clock.advance(61.0)
    limiter.sweep()

    assert "198.51.100.42" not in limiter._hits
    assert limiter.tracked_clients() == 0

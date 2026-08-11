"""Two requests for one unseen session must not both create an issue.

``synchronise`` reads the store, decides, and then writes. That sequence is not
atomic, and the window between the read and the write is exactly wide enough for
a second request carrying the same session to make the same decision. Both find
nothing, both recover nothing from GitHub, and both create — producing the
duplicate the whole idempotency model exists to prevent.

The first test here does not test the fix. It drives the unserialised sequence
directly and requires it to duplicate, because a concurrency test that passes
against both the broken and the fixed implementation proves nothing about
either. The rest require the application to serialise.

**Scope of the guarantee.** This serialises within one process. One issue per
session holds for the single-replica deployment the gateway documents. It is not
distributed coordination and does not claim to be; two replicas sharing an
intake repository could still race, and the deployment documentation says so.
"""

from __future__ import annotations

import threading

from conftest import SESSION_ID, FakeGitHub, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.concurrency import KeyedLocks
from nornyx_feedback_gateway.digest import compute_digest
from nornyx_feedback_gateway.models import FeedbackPayload
from nornyx_feedback_gateway.store import SyncStore
from nornyx_feedback_gateway.sync import synchronise

#: Long enough that a genuinely concurrent pair always meets; short enough that
#: a *serialised* pair pays it only once, when the barrier breaks.
RENDEZVOUS_SECONDS = 2.0


class RendezvousGitHub(FakeGitHub):
    """A sink that holds every caller at the lookup until its partner arrives.

    This is what makes the race deterministic rather than a matter of timing
    luck: without serialisation both threads are guaranteed to be past the
    lookup before either creates. Under serialisation the second thread never
    arrives, the barrier breaks on its timeout, and the first proceeds alone.
    """

    def __init__(self, parties: int = 2) -> None:
        super().__init__()
        self.barrier = threading.Barrier(parties)
        self.met = threading.Event()
        self._guard = threading.Lock()

    def find_issue(self, *, title: str, marker: str) -> int | None:
        # The lookup happens first and the rendezvous second, so both callers
        # hold the *same* answer — "nothing exists" — before either writes.
        # Rendezvousing first would let the second caller observe the first
        # caller's creation, which is the very interleaving being ruled out.
        answer = super().find_issue(title=title, marker=marker)
        try:
            self.barrier.wait(timeout=RENDEZVOUS_SECONDS)
            self.met.set()
        except threading.BrokenBarrierError:
            pass
        return answer

    def create_issue(self, *, title: str, body: str) -> int:
        # FakeGitHub's counter is not itself thread-safe; guarding it here keeps
        # the test measuring the gateway's behaviour rather than the fixture's.
        with self._guard:
            return super().create_issue(title=title, body=body)


def _run_both(target) -> list[BaseException | None]:
    errors: list[BaseException | None] = [None, None]

    def wrapped(index: int) -> None:
        try:
            target(index)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            errors[index] = exc

    threads = [threading.Thread(target=wrapped, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"
    return errors


# ------------------------------------------------- the race, before the fix
def test_the_unserialised_sequence_really_does_duplicate(tmp_path) -> None:
    """Demonstrate the defect the lock exists to close.

    ``synchronise`` is called directly from two threads with no serialisation —
    the shape the application had before this change. Both reach the create
    decision and both act on it.
    """

    sink = RendezvousGitHub()
    store = SyncStore(tmp_path / "gateway.db")
    payload = FeedbackPayload.model_validate(make_payload())
    digest = compute_digest(payload)

    errors = _run_both(
        lambda _: synchronise(
            payload, sink=sink, store=store, now="2026-08-10T12:00:00Z", digest=digest
        )
    )

    assert errors == [None, None]
    assert sink.met.is_set(), "the threads never actually overlapped"
    assert len(sink.issues) == 2, (
        "the unserialised sequence did not duplicate, so this test is not "
        "demonstrating the race the lock is meant to close"
    )


# -------------------------------------------------- the fix, through the app
def test_the_application_serialises_two_simultaneous_first_writes(config) -> None:
    sink = RendezvousGitHub()
    app = create_app(config=config, sink=sink)
    payload = make_payload()
    statuses: list[int] = [0, 0]
    outcomes: list[str] = ["", ""]

    def post(index: int) -> None:
        with TestClient(app) as api:
            response = api.post("/v1/feedback", json=payload)
        statuses[index] = response.status_code
        outcomes[index] = response.json().get("status", "")

    errors = _run_both(post)

    assert errors == [None, None]
    assert statuses == [202, 202], f"a concurrent request failed: {statuses}"
    assert len(sink.issues) == 1, "two simultaneous requests created two issues"
    assert sorted(outcomes) == ["created", "unchanged"], outcomes
    # Exactly one create reached GitHub.
    assert len([call for call in sink.calls if call[0] == "create"]) == 1


def test_the_second_writer_sees_the_first_writers_record(config) -> None:
    """Serialisation is only useful if the loser then reads what the winner wrote."""

    sink = RendezvousGitHub()
    app = create_app(config=config, sink=sink)
    payloads = [make_payload(clarity=4), make_payload(clarity=1)]
    outcomes: list[str] = ["", ""]

    def post(index: int) -> None:
        with TestClient(app) as api:
            outcomes[index] = api.post("/v1/feedback", json=payloads[index]).json()["status"]

    assert _run_both(post) == [None, None]
    assert len(sink.issues) == 1
    # Different content, so the loser must update rather than report unchanged.
    assert sorted(outcomes) == ["created", "updated"], outcomes


# ------------------------------------------------------------ positive control
def test_different_sessions_still_synchronise_independently(config) -> None:
    """Serialising by session must not serialise the service."""

    sink = FakeGitHub()
    app = create_app(config=config, sink=sink)
    sessions = [SESSION_ID, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"]
    outcomes: list[str] = ["", ""]

    def post(index: int) -> None:
        with TestClient(app) as api:
            outcomes[index] = api.post(
                "/v1/feedback", json=make_payload(session_id=sessions[index])
            ).json()["status"]

    assert _run_both(post) == [None, None]
    assert outcomes == ["created", "created"]
    assert len(sink.issues) == 2


def test_a_session_lock_is_released_so_later_requests_still_work(config, sink) -> None:
    with TestClient(create_app(config=config, sink=sink)) as api:
        first = api.post("/v1/feedback", json=make_payload(clarity=4))
        second = api.post("/v1/feedback", json=make_payload(clarity=2))
        third = api.post("/v1/feedback", json=make_payload(clarity=2))

    assert [first.json()["status"], second.json()["status"], third.json()["status"]] == [
        "created",
        "updated",
        "unchanged",
    ]


def test_a_github_failure_does_not_strand_the_session_lock(config, sink) -> None:
    """A raised error must not leave the session permanently unwritable."""

    from nornyx_feedback_gateway.github import GitHubError

    app = create_app(config=config, sink=sink)
    sink.fail_on["create_issue"] = GitHubError("timeout", "lost")
    with TestClient(app) as api:
        failed = api.post("/v1/feedback", json=make_payload())
        recovered = api.post("/v1/feedback", json=make_payload())

    assert failed.status_code == 503
    assert recovered.status_code == 202, "the session lock was never released"
    assert app.state.session_locks.tracked_keys() == 0


# ------------------------------------------------------------------ the lock
def test_keyed_locks_exclude_the_same_key_and_admit_different_ones() -> None:
    locks = KeyedLocks()
    inside = threading.Event()
    release = threading.Event()
    observed: list[str] = []

    def hold_a() -> None:
        with locks.hold("a"):
            inside.set()
            release.wait(timeout=5)
            observed.append("a-done")

    def wait_a() -> None:
        inside.wait(timeout=5)
        with locks.hold("a"):
            observed.append("a-second")

    def take_b() -> None:
        inside.wait(timeout=5)
        with locks.hold("b"):
            observed.append("b-independent")

    threads = [threading.Thread(target=fn) for fn in (hold_a, wait_a, take_b)]
    for thread in threads:
        thread.start()
    # "b" is a different key and must not be blocked by the holder of "a".
    threading.Event().wait(0.2)
    assert "b-independent" in observed
    assert "a-second" not in observed
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert observed.index("a-done") < observed.index("a-second")


def test_keyed_locks_do_not_accumulate_entries() -> None:
    """Bounded by concurrent holders, not by keys ever seen."""

    locks = KeyedLocks()
    for index in range(5_000):
        with locks.hold(f"session-{index}"):
            pass
    assert locks.tracked_keys() == 0

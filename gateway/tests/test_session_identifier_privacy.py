"""The identifier that authorises a write must never be published.

The intake is unauthenticated by design, so presenting a session's UUID is what
lets a caller overwrite that session's issue. That was tolerable only while the
UUID stayed private — and it did not. The rendered issue published it three
times: in the summary line, in the HTML recovery marker, and in the embedded
JSON. Against a public intake repository, the issue published the exact locator
needed to overwrite itself.

The separation now enforced:

    session UUID          private write key, Academy -> gateway only
    sha256(session UUID)  public correlation marker, safe to publish

Everything GitHub sees is the marker. Recovery still works because the
derivation is deterministic, which these tests require alongside the absence.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest
from conftest import EXPECTED_TITLE, SESSION_ID, SESSION_MARKER, FakeGitHub, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.config import GatewayConfig
from nornyx_feedback_gateway.github import GitHubError
from nornyx_feedback_gateway.identity import derive_marker, title_fragment
from nornyx_feedback_gateway.store import SyncStore

OTHER_SESSION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _publish(config, sink, payload=None) -> str:
    with TestClient(create_app(config=config, sink=sink)) as api:
        response = api.post("/v1/feedback", json=payload or make_payload())
    assert response.status_code == 202, response.text
    return sink.issues[1]["body"]


# --------------------------------------------------------------- the absence
def test_the_session_uuid_appears_nowhere_in_the_published_issue(config, sink) -> None:
    """The headline requirement, over the whole artefact."""

    body = _publish(config, sink)
    title = sink.issues[1]["title"]

    assert SESSION_ID not in body, "the write key was published in the issue body"
    assert SESSION_ID not in title
    # Not even in pieces: the old title exposed the UUID's first eight hex
    # characters, which is UUID material regardless of how little of it.
    assert SESSION_ID[:8] not in body
    assert SESSION_ID[:8] not in title


@pytest.mark.parametrize(
    "section",
    ["summary", "marker comment", "machine-readable payload"],
)
def test_each_place_that_used_to_carry_the_uuid_now_carries_the_marker(
    config, sink, section
) -> None:
    body = _publish(config, sink)

    if section == "summary":
        line = next(line for line in body.split("\n") if line.startswith("- Session marker:"))
        assert SESSION_MARKER in line
        assert SESSION_ID not in line
    elif section == "marker comment":
        assert f"<!-- nornyx-feedback-session: {SESSION_MARKER} -->" in body
        assert f"nornyx-feedback-session: {SESSION_ID}" not in body
    else:
        document = json.loads(body.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        assert document["session"]["session_marker"] == SESSION_MARKER
        assert "session_id" not in document["session"]


def test_the_public_issue_contains_nothing_the_gateway_accepts_as_a_session_id(
    config, sink
) -> None:
    """The property that actually matters: no readable value is a valid write key.

    Sweep the published issue for anything shaped like the identifier the wire
    contract accepts, and require that none of it is the real one. A reader of a
    public intake repository must come away unable to address the session.
    """

    body = _publish(config, sink)
    uuid_shaped = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", body)

    assert uuid_shaped == [], f"the issue publishes UUID-shaped values: {uuid_shaped}"
    # And the marker that *is* published cannot be turned back into one.
    assert derive_marker(SESSION_ID) == SESSION_MARKER
    assert SESSION_MARKER != SESSION_ID


def test_the_marker_is_one_way_and_collision_free_across_sessions() -> None:
    first = derive_marker(SESSION_ID)
    second = derive_marker(OTHER_SESSION)

    assert first != second
    assert len(first) == 64 and re.fullmatch(r"[0-9a-f]{64}", first)
    # Derivation is a plain digest of the identifier, reproducible by anyone —
    # which is what lets recovery work without gateway-held state.
    assert first == hashlib.sha256(SESSION_ID.encode("utf-8")).hexdigest()
    # Knowing the marker does not reveal the identifier.
    assert SESSION_ID not in first


def test_different_sessions_publish_different_titles_and_markers(config) -> None:
    sink = FakeGitHub()
    with TestClient(create_app(config=config, sink=sink)) as api:
        api.post("/v1/feedback", json=make_payload(session_id=SESSION_ID))
        api.post("/v1/feedback", json=make_payload(session_id=OTHER_SESSION))

    titles = {issue["title"] for issue in sink.issues.values()}
    assert len(titles) == 2
    assert EXPECTED_TITLE in titles
    assert title_fragment(derive_marker(OTHER_SESSION)) in " ".join(titles)


# -------------------------------------------------------------- the recovery
def test_recovery_after_gateway_database_loss_still_finds_the_issue(config, sink, tmp_path) -> None:
    """The marker has to be derivable, not remembered — this is why."""

    with TestClient(create_app(config=config, sink=sink)) as api:
        first = api.post("/v1/feedback", json=make_payload(clarity=4))
    assert first.json()["status"] == "created"

    lost = GatewayConfig(
        github_repository=config.github_repository,
        github_token=config.github_token,
        database_path=str(tmp_path / "rebuilt-from-nothing.db"),
        destination_visibility="private",
    )
    with TestClient(create_app(config=lost, sink=sink)) as api:
        second = api.post("/v1/feedback", json=make_payload(clarity=1))

    assert second.json()["status"] == "updated"
    assert second.json()["issue_number"] == first.json()["issue_number"]
    assert len(sink.issues) == 1


def test_the_same_session_always_maps_to_the_same_issue(config, sink) -> None:
    with TestClient(create_app(config=config, sink=sink)) as api:
        numbers = [
            api.post("/v1/feedback", json=make_payload(clarity=clarity)).json()["issue_number"]
            for clarity in (4, 3, 2, 1)
        ]

    assert len(set(numbers)) == 1
    assert len(sink.issues) == 1


def test_an_ambiguous_create_retry_is_still_idempotent(config, sink) -> None:
    """The write lands on GitHub, the response is lost, the client retries."""

    sink.create_then_fail = GitHubError("timeout", "response lost after the write")
    with TestClient(create_app(config=config, sink=sink)) as api:
        lost = api.post("/v1/feedback", json=make_payload())
        assert lost.status_code == 503
        assert len(sink.issues) == 1

        retry = api.post("/v1/feedback", json=make_payload())

    assert retry.json()["status"] == "updated"
    assert retry.json()["issue_number"] == 1
    assert len(sink.issues) == 1


def test_recovery_matches_on_the_marker_not_on_the_uuid(config, sink) -> None:
    """A marker that did not identify the session would silently duplicate."""

    with TestClient(create_app(config=config, sink=sink)) as api:
        api.post("/v1/feedback", json=make_payload())

    _, title = next(call for call in sink.calls if call[0] == "create")
    assert title == EXPECTED_TITLE
    assert SESSION_MARKER in sink.issues[1]["body"]


# ------------------------------------------------------------------- storage
def test_the_gateway_database_does_not_persist_the_write_key(config, sink, tmp_path) -> None:
    """Nothing downstream should hold a value that authorises a write."""

    import sqlite3

    with TestClient(create_app(config=config, sink=sink)) as api:
        api.post("/v1/feedback", json=make_payload())

    with sqlite3.connect(config.database_path) as connection:
        rows = connection.execute("SELECT * FROM feedback_sessions").fetchall()
        columns = [row[1] for row in connection.execute("PRAGMA table_info(feedback_sessions)")]

    assert "session_marker" in columns
    assert "session_id" not in columns
    flattened = " ".join(str(value) for row in rows for value in row)
    assert SESSION_ID not in flattened
    assert SESSION_MARKER in flattened


def test_a_pre_release_store_keyed_by_uuid_is_discarded(tmp_path) -> None:
    """Carrying the old keys forward would defeat the change."""

    import sqlite3

    database = tmp_path / "pre-release.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE feedback_sessions (
                session_id TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                payload_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO feedback_sessions VALUES (?, 7, 'sha256:x', 'now', 'now')",
            (SESSION_ID,),
        )

    SyncStore(database)

    with sqlite3.connect(database) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(feedback_sessions)")]
        remaining = connection.execute("SELECT COUNT(*) FROM feedback_sessions").fetchone()[0]

    assert "session_marker" in columns and "session_id" not in columns
    assert remaining == 0, "old rows carried the write key forward"


def test_losing_the_cache_costs_nothing_because_recovery_exists(config, sink, tmp_path) -> None:
    """Positive control for discarding the old table rather than migrating it."""

    with TestClient(create_app(config=config, sink=sink)) as api:
        api.post("/v1/feedback", json=make_payload())

    empty = GatewayConfig(
        github_repository=config.github_repository,
        github_token=config.github_token,
        database_path=str(tmp_path / "empty.db"),
    )
    with TestClient(create_app(config=empty, sink=sink)) as api:
        again = api.post("/v1/feedback", json=make_payload(clarity=2))

    assert again.json()["status"] == "updated"
    assert len(sink.issues) == 1

"""The digest must be something the gateway derives, not something it is told.

``sync.payload_digest`` arrives inside an unauthenticated request. Trusting it
hands the sender control of content identity, and content identity is what
decides whether a payload is a no-op, an update, or a create. Two concrete
consequences, both attacked below: a stale digest attached to changed content
makes the gateway skip an update it should have made, and an attacker-chosen
digest lets one payload claim another's identity.

The fixture computes the digest with its own statement of the rule, so
"the correct digest is accepted" is a genuine agreement between two
implementations rather than the gateway agreeing with itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import SESSION_ID, digest_of, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.digest import (
    DigestMismatch,
    canonical_body,
    compute_digest,
    verified_digest,
)
from nornyx_feedback_gateway.models import FeedbackPayload

GOLDEN = Path(__file__).parent / "academy_payload.golden.json"
ZEROED = "sha256:" + "0" * 64


def _post(config, sink, payload):
    with TestClient(create_app(config=config, sink=sink)) as api:
        return api.post("/v1/feedback", json=payload)


# ------------------------------------------------------------------- positive
def test_a_correct_digest_is_accepted(config, sink) -> None:
    response = _post(config, sink, make_payload())

    assert response.status_code == 202, response.text
    assert len(sink.issues) == 1


def test_the_gateway_agrees_with_a_real_academy_payload(config, sink) -> None:
    """Cross-implementation proof, without needing both packages installed.

    The fixture is a payload a real Academy actually produced, digest and all.
    If either side's canonicalisation drifts — key ordering, separators, which
    fields are emitted, how ``None`` is rendered — this fails, which is the
    point: a digest only one implementation can reproduce verifies nothing.
    """

    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    stamped = payload["sync"]["payload_digest"]

    assert compute_digest(FeedbackPayload.model_validate(payload)) == stamped
    assert digest_of(payload) == stamped

    response = _post(config, sink, payload)
    assert response.status_code == 202, response.text


def test_key_order_on_the_wire_does_not_change_the_recomputed_digest(config, sink) -> None:
    """Canonicalisation, not incidental JSON layout, decides identity."""

    payload = make_payload()
    shuffled = json.loads(json.dumps(payload, sort_keys=True))
    reversed_keys = dict(reversed(list(payload.items())))

    first = compute_digest(FeedbackPayload.model_validate(payload))
    second = compute_digest(FeedbackPayload.model_validate(shuffled))
    third = compute_digest(FeedbackPayload.model_validate(reversed_keys))

    assert first == second == third
    assert _post(config, sink, reversed_keys).status_code == 202


# ------------------------------------------------------------------- attacks
def test_a_syntactically_valid_but_wrong_digest_is_refused(config, sink) -> None:
    payload = make_payload()
    payload["sync"]["payload_digest"] = ZEROED

    response = _post(config, sink, payload)

    assert response.status_code == 422
    assert response.json()["code"] == "digest_mismatch"
    assert sink.calls == [], "a forged digest reached the GitHub boundary"


@pytest.mark.parametrize(
    ("description", "mutate"),
    [
        ("clarity", lambda p: p["module_feedback"][0]["perception"].update({"clarity": 1})),
        ("comment", lambda p: p["module_feedback"][0]["perception"].update({"comment": "other"})),
        (
            "assessment pass",
            lambda p: p["module_feedback"][0]["academy_context"].update(
                {"assessment_passed": False}
            ),
        ),
        ("module id", lambda p: p["module_feedback"][0].update({"module_id": "F1"})),
        ("academy version", lambda p: p["runtime"].update({"academy_version": "9.9.9"})),
        (
            "course recommendation",
            lambda p: p["course_feedback"]["perception"].update({"recommend": "no"}),
        ),
        (
            "session opened at",
            lambda p: p["session"].update({"created_at": "2020-01-01T00:00:00Z"}),
        ),
    ],
)
def test_content_mutated_under_a_retained_digest_is_refused(
    config, sink, description, mutate
) -> None:
    """The stale-digest attack, field by field.

    Keeping the old digest while changing the content is how a sender would make
    the gateway believe an already-written session is unchanged and skip the
    update — or, on a first write, record content under an identity that does
    not describe it.
    """

    payload = make_payload()
    mutate(payload)  # digest deliberately left as it was

    response = _post(config, sink, payload)

    assert response.status_code == 422, f"{description} passed with a stale digest"
    assert response.json()["code"] == "digest_mismatch"
    assert sink.calls == []


def test_the_refusal_happens_before_the_sync_store_is_touched(config, sink, tmp_path) -> None:
    import sqlite3

    payload = make_payload()
    payload["sync"]["payload_digest"] = ZEROED
    assert _post(config, sink, payload).status_code == 422

    with sqlite3.connect(config.database_path) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM feedback_sessions").fetchone()[0]
    assert rows == 0, "a rejected payload was recorded in the synchronisation store"


def test_a_forged_digest_cannot_suppress_a_genuine_update(config, sink) -> None:
    """The consequence that matters: an update the gateway would otherwise make.

    Write a session, then send changed content carrying the *first* payload's
    digest. Trusting the submitted value would classify this as ``unchanged``
    and silently drop the learner's revision.
    """

    first = make_payload(clarity=4)
    assert _post(config, sink, first).status_code == 202
    body_before = sink.issues[1]["body"]

    stale = make_payload(clarity=1)
    stale["sync"]["payload_digest"] = first["sync"]["payload_digest"]
    response = _post(config, sink, stale)

    assert response.status_code == 422
    assert sink.issues[1]["body"] == body_before

    # The same change with an honest digest is accepted and does update.
    honest = make_payload(clarity=1)
    assert _post(config, sink, honest).json()["status"] == "updated"
    assert sink.issues[1]["body"] != body_before


def test_idempotency_uses_the_recomputed_digest(config, sink) -> None:
    """Two payloads that differ only in their claimed digest are not the same record."""

    payload = make_payload()
    assert _post(config, sink, payload).json()["status"] == "created"

    # Identical content, honest digest: unchanged, and no edit is written.
    assert _post(config, sink, make_payload()).json()["status"] == "unchanged"
    assert [call for call in sink.calls if call[0] == "update"] == []


# --------------------------------------------------------------------- units
def test_the_canonical_body_excludes_only_the_sync_envelope() -> None:
    payload = FeedbackPayload.model_validate(make_payload())
    document = json.loads(canonical_body(payload))

    assert "sync" not in document
    assert set(document) == {
        "schema_id",
        "session",
        "runtime",
        "module_feedback",
        "course_feedback",
    }


def test_the_generation_timestamp_cannot_change_the_digest() -> None:
    """Otherwise an unchanged session would look changed on every regeneration."""

    first = make_payload()
    second = make_payload()
    second["sync"]["generated_at"] = "2027-01-01T00:00:00Z"
    second["sync"]["payload_digest"] = first["sync"]["payload_digest"]

    assert compute_digest(FeedbackPayload.model_validate(first)) == compute_digest(
        FeedbackPayload.model_validate(second)
    )


def test_verified_digest_raises_with_both_values_available_for_logging() -> None:
    payload = make_payload()
    payload["sync"]["payload_digest"] = ZEROED
    model = FeedbackPayload.model_validate(payload)

    with pytest.raises(DigestMismatch) as caught:
        verified_digest(model)

    assert caught.value.submitted == ZEROED
    assert caught.value.expected == compute_digest(model)
    # The message stays generic; neither value is interpolated into it.
    assert ZEROED not in str(caught.value)


def test_a_session_id_change_changes_the_digest() -> None:
    other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    assert compute_digest(
        FeedbackPayload.model_validate(make_payload(session_id=SESSION_ID))
    ) != compute_digest(FeedbackPayload.model_validate(make_payload(session_id=other)))

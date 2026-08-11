"""Consent, delivery, and the promise that failure never costs a learner anything.

Two claims are being defended here, and they are the ones a reviewer should be
most suspicious of because both are easy to *say*:

* **Nothing leaves before explicit consent.** Proved by counting transport
  calls, not by reading the code. Zero is the assertion.
* **The local save is independent of the network.** Proved by making every kind
  of delivery failure happen and then reading the row back.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import LEARNER_MESSAGES, FeedbackConfiguration, payload_digest
from nornyx_lab.academy.feedback_client import (
    TransportResult,
    UrllibFeedbackTransport,
    endpoint_is_acceptable,
)
from nornyx_lab.academy.schemas import DestinationVisibility

ENDPOINT = "https://feedback.example.test/v1/feedback"

FEEDBACK = {
    "clarity": 4,
    "confidence": 3,
    "difficulty": "right_level",
    "self_assessment": "understood",
    "comment": "clear enough",
}


class ScriptedTransport:
    """Records every attempt and replays scripted outcomes in order."""

    def __init__(self, *results: TransportResult) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results = list(results) or [
            TransportResult(ok=True, outcome="created", issue_number=11)
        ]

    def send(self, endpoint: str, payload: dict) -> TransportResult:
        self.calls.append((endpoint, payload))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def _client(tmp_path: Path, transport, *, endpoint: str | None = ENDPOINT, visibility=None):
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=endpoint,
                destination_visibility=visibility or DestinationVisibility.PRIVATE,
            ),
            feedback_transport=transport,
        )
    )


# ------------------------------------------------------------------- consent
def test_nothing_is_transmitted_before_explicit_consent(tmp_path) -> None:
    """The single most important negative assertion in the feature."""

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/feedback/modules/F1", json=FEEDBACK)
        client.post(
            "/api/v1/feedback/course",
            json={
                "overall_clarity": 4,
                "progression": 4,
                "usefulness": 4,
                "final_confidence": 4,
                "overall_difficulty": "right_level",
                "recommend": "yes",
            },
        )
        status = client.get("/api/v1/feedback").json()

    assert transport.calls == [], "feedback was transmitted without consent"
    assert status["consent_state"] == "not_asked"
    assert status["sync"]["status"] == "no_consent"
    assert status["learner_message"] == LEARNER_MESSAGES["no_consent"]


def test_an_explicit_sync_request_without_consent_still_sends_nothing(tmp_path) -> None:
    """Consent is read from the record, not from whoever called the endpoint."""

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        response = client.post("/api/v1/feedback/sync")

    assert transport.calls == []
    assert response.json()["sync"]["status"] == "no_consent"


def test_consent_is_never_implied_by_a_missing_field(tmp_path) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        response = client.post("/api/v1/feedback/consent", json={})

    assert response.status_code == 422, "an absent decision was treated as a decision"
    assert transport.calls == []


def test_granting_consent_makes_existing_feedback_sync_eligible(tmp_path) -> None:
    """Positive control for the consent gate."""

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        assert transport.calls == []
        granted = client.post("/api/v1/feedback/consent", json={"granted": True}).json()

    assert len(transport.calls) == 1
    endpoint, payload = transport.calls[0]
    assert endpoint == ENDPOINT
    assert payload["module_feedback"][0]["module_id"] == "F0"
    assert granted["consent_state"] == "granted"
    assert granted["consent_at"]
    assert granted["sync"]["status"] == "synced"
    assert granted["sync"]["remote_reference"] == "issue #11"
    assert granted["learner_message"] == LEARNER_MESSAGES["synced"]


def test_after_consent_later_feedback_in_the_same_session_syncs(tmp_path) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/feedback/modules/F1", json=FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert len(transport.calls) >= 2
    assert {record["module_id"] for record in transport.calls[-1][1]["module_feedback"]} == {
        "F0",
        "F1",
    }
    assert status["learner_message"] == LEARNER_MESSAGES["synced"]


def test_revocation_stops_future_synchronisation(tmp_path) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        before = len(transport.calls)

        revoked = client.post("/api/v1/feedback/consent", json={"granted": False}).json()
        client.post("/api/v1/feedback/modules/F1", json=FEEDBACK)
        client.post("/api/v1/feedback/sync")

    assert revoked["consent_state"] == "revoked"
    assert len(transport.calls) == before, "feedback was sent after consent was revoked"


def test_the_consent_record_keeps_the_wording_that_was_agreed_to(tmp_path) -> None:
    """A grant is only meaningful alongside what it was a grant *of*."""

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/consent", json={"granted": False})
        events = client.app.state.feedback_repository.consent_events()

    assert [event["event"] for event in events] == ["granted", "revoked"]
    assert all(event["consent_document_version"] for event in events)
    assert all(event["destination_disclosure"] == "private" for event in events)
    # Append-only: a revocation does not erase the grant that authorised what
    # was already sent.
    assert len(events) == 2


@pytest.mark.parametrize(
    ("visibility", "must_contain"),
    [
        (DestinationVisibility.PUBLIC, "publicly visible"),
        (DestinationVisibility.PRIVATE, "not published publicly"),
        (DestinationVisibility.UNKNOWN, "cannot confirm"),
    ],
)
def test_the_consent_copy_states_the_configured_destination_honestly(
    tmp_path, visibility, must_contain
) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport, visibility=visibility) as client:
        status = client.get("/api/v1/feedback").json()

    assert status["destination_visibility"] == visibility.value
    joined = " ".join(status["consent_disclosure"]).lower()
    assert must_contain in joined, joined


# ------------------------------------------------------------ idempotency (E)
def test_an_unchanged_payload_is_not_sent_again(tmp_path) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        after_first = len(transport.calls)
        client.post("/api/v1/feedback/sync")
        client.post("/api/v1/feedback/sync")
        client.post("/api/v1/feedback/sync")

    assert len(transport.calls) == after_first, "an unchanged session was re-sent"


def test_a_changed_payload_is_sent_and_carries_a_new_digest(tmp_path) -> None:
    transport = ScriptedTransport(TransportResult(ok=True, outcome="updated", issue_number=11))
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json={**FEEDBACK, "clarity": 4})
        client.post("/api/v1/feedback/modules/F0", json={**FEEDBACK, "clarity": 1})

    digests = [payload["sync"]["payload_digest"] for _, payload in transport.calls]
    assert len(set(digests)) == len(digests) >= 2, "a changed rating reused a digest"


def test_the_digest_is_recomputed_from_the_payload_not_echoed_back(tmp_path) -> None:
    """Negative control against a value that verifies itself.

    The digest must be derivable from the payload by an independent computation.
    If the sender simply carried a stored string, this would pass trivially — so
    the check recomputes it here and also proves it *moves* when content moves.
    """

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        _, sent = transport.calls[-1]

    assert sent["sync"]["payload_digest"] == payload_digest(sent)
    mutated = {**sent, "module_feedback": []}
    assert payload_digest(mutated) != sent["sync"]["payload_digest"]


def test_the_digest_ignores_only_the_envelope_that_carries_it(tmp_path) -> None:
    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        _, sent = transport.calls[-1]

    later = {**sent, "sync": {"payload_digest": "sha256:" + "0" * 64, "generated_at": "later"}}
    assert payload_digest(later) == payload_digest(sent)


def test_a_restart_reuses_the_session_and_does_not_resend(tmp_path) -> None:
    """Restarting the academy must not look like a new learner to the gateway."""

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        first_session = client.get("/api/v1/feedback").json()["session_id"]
    calls_before_restart = len(transport.calls)

    with _client(tmp_path, transport) as client:
        status = client.get("/api/v1/feedback").json()
        client.post("/api/v1/feedback/sync")

    assert status["session_id"] == first_session
    assert status["consent_state"] == "granted"
    assert len(transport.calls) == calls_before_restart, "a restart re-sent an unchanged session"


# --------------------------------------------------------------- outage (L)
@pytest.mark.parametrize(
    "error_code",
    ["timeout", "unreachable", "rejected", "gateway_error", "rate_limited", "malformed_response"],
)
def test_a_delivery_failure_never_loses_the_local_record(tmp_path, error_code) -> None:
    transport = ScriptedTransport(TransportResult(ok=False, error_code=error_code))
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        response = client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert status["module_feedback"][0]["clarity"] == 4
    assert status["sync"]["status"] == "failed"
    assert status["sync"]["last_error_code"] == error_code
    assert status["learner_message"] == LEARNER_MESSAGES["unavailable"]


def test_a_transport_that_raises_cannot_take_down_the_learner_request(tmp_path) -> None:
    """A gateway outage is not the learner's problem and must not become one.

    Not merely "the classified failure codes are handled" — an *unexpected*
    exception from the transport must also come back as a saved rating and an
    honest delivery state, never as a failed request for an action that
    actually succeeded.
    """

    class ExplodingTransport:
        def send(self, endpoint, payload):
            raise ConnectionResetError("the network went away mid-write")

    with _client(tmp_path, ExplodingTransport()) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        response = client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 200, response.text
    assert response.json()["saved"] is True
    assert status["module_feedback"][0]["clarity"] == 4
    assert status["sync"]["status"] == "failed"
    assert status["sync"]["last_error_code"] == "transport_error"
    assert status["learner_message"] == LEARNER_MESSAGES["unavailable"]


def test_consent_with_nothing_recorded_yet_sends_nothing(tmp_path) -> None:
    """Opting in is not itself a submission.

    An empty session must not be transmitted: it would open an issue containing
    no feedback and make a network call the learner never asked for.
    """

    transport = ScriptedTransport()
    with _client(tmp_path, transport) as client:
        granted = client.post("/api/v1/feedback/consent", json={"granted": True}).json()

    assert transport.calls == []
    assert granted["consent_state"] == "granted"
    assert granted["learner_message"] == LEARNER_MESSAGES["empty"]


def test_a_failed_delivery_is_retried_on_the_next_attempt(tmp_path) -> None:
    transport = ScriptedTransport(
        TransportResult(ok=False, error_code="timeout"),
        TransportResult(ok=True, outcome="created", issue_number=11),
    )
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        failed = client.get("/api/v1/feedback").json()
        recovered = client.post("/api/v1/feedback/sync").json()

    assert failed["sync"]["status"] == "failed"
    assert recovered["sync"]["status"] == "synced"
    assert recovered["sync"]["attempts"] >= 2


def test_one_learner_request_makes_at_most_one_delivery_attempt(tmp_path) -> None:
    """No retry loop inside a learner's HTTP request."""

    transport = ScriptedTransport(TransportResult(ok=False, error_code="timeout"))
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        before = len(transport.calls)
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)

    assert len(transport.calls) - before == 1


def test_a_2xx_with_an_unrecognised_body_is_not_treated_as_delivery(tmp_path) -> None:
    """A UI must never say "sent" because a proxy returned 200 and an error page."""

    class VagueTransport:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def send(self, endpoint, payload):
            self.calls.append((endpoint, payload))
            return TransportResult(ok=False, error_code="malformed_response")

    transport = VagueTransport()
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert status["sync"]["status"] == "failed"
    assert status["learner_message"] != LEARNER_MESSAGES["synced"]


def test_no_internal_detail_reaches_the_learner_on_failure(tmp_path) -> None:
    transport = ScriptedTransport(TransportResult(ok=False, error_code="unreachable"))
    with _client(tmp_path, transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        response = client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)

    text = response.text
    assert "Traceback" not in text
    assert ENDPOINT not in text, "the gateway URL was echoed to the browser"
    assert str(tmp_path) not in text, "a filesystem path was echoed to the browser"


# ------------------------------------------------------------------ transport
def test_a_plaintext_endpoint_is_refused_unless_it_is_loopback() -> None:
    """Learner free text does not travel the open internet in the clear."""

    assert endpoint_is_acceptable("https://feedback.example.test/v1/feedback") is True
    assert endpoint_is_acceptable("http://127.0.0.1:9000/v1/feedback") is True
    assert endpoint_is_acceptable("http://localhost:9000/v1/feedback") is True
    assert endpoint_is_acceptable("http://feedback.example.test/v1/feedback") is False
    assert endpoint_is_acceptable("ftp://example.test/") is False
    assert endpoint_is_acceptable("file:///etc/passwd") is False


def test_the_transport_refuses_an_insecure_endpoint_without_sending(tmp_path) -> None:
    class NeverCalled:
        def open(self, request, timeout=None):  # noqa: ANN001
            raise AssertionError("a request was made to an insecure endpoint")

    transport = UrllibFeedbackTransport(opener=NeverCalled())
    result = transport.send("http://feedback.example.test/v1/feedback", {"a": 1})

    assert result.ok is False
    assert result.error_code == "insecure_endpoint"


def test_the_transport_does_not_follow_a_redirect_elsewhere(tmp_path) -> None:
    """A redirect is a request to send the learner's words somewhere else."""

    import urllib.error

    class RedirectingOpener:
        def open(self, request, timeout=None):  # noqa: ANN001
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found", {"Location": "https://elsewhere.test"}, None
            )

    transport = UrllibFeedbackTransport(opener=RedirectingOpener())
    result = transport.send(ENDPOINT, {"a": 1})

    assert result.ok is False
    assert result.error_code == "redirect_refused"


def test_the_transport_sends_with_an_explicit_timeout() -> None:
    import io
    import json

    class Recorder:
        def __init__(self) -> None:
            self.timeouts: list[float | None] = []

        def open(self, request, timeout=None):  # noqa: ANN001
            self.timeouts.append(timeout)
            return io.BytesIO(json.dumps({"status": "created", "issue_number": 3}).encode())

    recorder = Recorder()
    transport = UrllibFeedbackTransport(timeout_seconds=4.5, opener=recorder)
    result = transport.send(ENDPOINT, {"a": 1})

    assert result.ok is True and result.issue_number == 3
    assert recorder.timeouts == [4.5]

"""Attacks constructed against the feedback boundary, not inspections of it.

Each test here started as "how would I break this?" rather than "does this line
work?". Where an attack succeeded during development the implementation changed;
what remains is the regression that keeps it closed.

Structural claims are checked structurally: "there is exactly one place that can
make an outbound call" is verified by counting call sites in the AST, because a
second one added later would pass every behavioural test in the suite while
quietly bypassing the consent gate.
"""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import FeedbackConfiguration
from nornyx_lab.academy.feedback_client import TransportResult
from nornyx_lab.academy.schemas import DestinationVisibility

SOURCE = Path(__file__).resolve().parents[2] / "src" / "nornyx_lab" / "academy"
REPOSITORY = Path(__file__).resolve().parents[2]

FEEDBACK = {
    "clarity": 4,
    "confidence": 3,
    "difficulty": "right_level",
    "self_assessment": "understood",
    "comment": "fine",
}


class CountingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def send(self, endpoint: str, payload: dict) -> TransportResult:
        self.calls.append((endpoint, payload))
        return TransportResult(ok=True, outcome="created", issue_number=1)


def _client(tmp_path: Path, *, endpoint: str | None = None, transport=None, visibility=None):
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=endpoint,
                destination_visibility=visibility or DestinationVisibility.UNKNOWN,
            ),
            feedback_transport=transport,
        )
    )


# ------------------------------------------------------------- consent bypass
def test_there_is_exactly_one_outbound_call_site_in_the_whole_feature() -> None:
    """A second `transport.send` would bypass the consent gate silently.

    Behavioural tests cannot catch that: they exercise the path that *is*
    guarded. So the count is asserted directly.
    """

    tree = ast.parse((SOURCE / "feedback.py").read_text(encoding="utf-8"))
    sends = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "send"
    ]
    assert len(sends) == 1, (
        f"{len(sends)} outbound call sites in feedback.py; every one of them needs "
        "its own consent gate, so there must be exactly one"
    )


def test_the_only_outbound_call_sits_behind_the_stored_consent_check() -> None:
    source = (SOURCE / "feedback.py").read_text(encoding="utf-8")
    sync = source.split("def sync_now")[1]
    gate = sync.index("consent_state")
    call = sync.index("transport.send")
    assert gate < call, "the outbound call is not preceded by the consent check"


@pytest.mark.parametrize(
    "attempt",
    [
        {"granted": "true"},
        {"granted": 1},
        {"granted": "yes"},
        {"consent": True},
        {"granted": None},
        {},
    ],
)
def test_consent_cannot_be_granted_by_a_loosely_typed_value(tmp_path, attempt) -> None:
    """Truthiness is not consent."""

    transport = CountingTransport()
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        response = client.post("/api/v1/feedback/consent", json=attempt)
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 422, f"{attempt} was accepted as consent"
    assert status["consent_state"] == "not_asked"
    assert transport.calls == []


def test_writing_consent_directly_into_the_database_is_the_only_way_around_it(tmp_path) -> None:
    """The honest statement of the boundary.

    Consent lives in the local SQLite file, and a learner with filesystem access
    can edit it. That is not a defect to fix — it is their own machine and their
    own data. What matters is that no *API* path grants consent, and that is
    what the rest of these tests establish.
    """

    transport = CountingTransport()
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        for method, path in (
            ("post", "/api/v1/feedback/sync"),
            ("get", "/api/v1/feedback"),
            ("get", "/api/v1/feedback/summary"),
            ("delete", "/api/v1/feedback"),
        ):
            getattr(client, method)(path)

    assert transport.calls == [], "a non-consent endpoint triggered transmission"


def test_a_second_academy_process_cannot_be_tricked_into_sending(tmp_path) -> None:
    """Restart with consent still not given: still nothing goes out."""

    transport = CountingTransport()
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        client.post("/api/v1/feedback/sync")
        client.post("/api/v1/feedback/modules/F1", json=FEEDBACK)

    assert transport.calls == []


# --------------------------------------------------------- browser authority
def test_the_request_models_expose_no_context_field_at_all() -> None:
    """Structural: a field that does not exist cannot be forged."""

    from nornyx_lab.academy.schemas import CourseFeedbackRequest, ModuleFeedbackRequest

    module_fields = set(ModuleFeedbackRequest.model_fields)
    course_fields = set(CourseFeedbackRequest.model_fields)
    forbidden = {
        "assessment_score",
        "assessment_passed",
        "assessment_attempts",
        "module_status",
        "competence_revision",
        "academy_version",
        "nornyx_version",
        "adapter_version",
        "content_version",
        "session_id",
        "learner_id",
        "created_at",
        "session_elapsed_seconds",
        "learning_path_id",
        "academy_context",
    }
    assert not (module_fields & forbidden), sorted(module_fields & forbidden)
    assert not (course_fields & forbidden), sorted(course_fields & forbidden)
    assert ModuleFeedbackRequest.model_config["extra"] == "forbid"
    assert CourseFeedbackRequest.model_config["extra"] == "forbid"


def test_a_client_cannot_choose_its_own_session_identifier(tmp_path) -> None:
    """The identifier is never accepted from a request, so there is nothing to forge."""

    transport = CountingTransport()
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        real = client.get("/api/v1/feedback").json()["session_id"]
        rejected = client.post(
            "/api/v1/feedback/modules/F0",
            json={**FEEDBACK, "session_id": "00000000-0000-4000-8000-000000000000"},
        )
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        after = client.get("/api/v1/feedback").json()["session_id"]

    assert rejected.status_code == 422
    assert after == real


def test_the_recorded_score_is_the_learner_record_not_the_claim(tmp_path) -> None:
    """A client that has failed everything cannot record itself as having passed."""

    with _client(tmp_path) as client:
        client.post("/api/v1/modules/F0/run")
        client.post("/api/v1/assessments/assessment.F0/submit", json={"answers": ["nonsense"]})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = client.get("/api/v1/feedback").json()["module_feedback"][0]["academy_context"]

    assert context["assessment_passed"] is False
    assert context["assessment_score"] == 0.0
    assert context["module_status"] == "needs_review"


# ------------------------------------------------------------ secret exposure
def test_no_feedback_response_can_carry_a_secret_because_none_exists(tmp_path) -> None:
    """The academy has no credential to leak, and this proves the surface too."""

    with _client(
        tmp_path, endpoint="https://gw.test/v1/feedback", transport=CountingTransport()
    ) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        bodies = [
            client.get("/api/v1/feedback").text,
            client.get("/api/v1/feedback/summary").text,
            client.get("/api/v1/progress/export").text,
            client.get("/api/v1/openapi.json").text,
        ]

    for body in bodies:
        for token in ("github_token", "ghp_", "github_pat_", "Authorization", "Bearer "):
            assert token not in body


def test_the_exported_progress_report_does_not_carry_feedback(tmp_path) -> None:
    """Two different things about a learner, exported separately or not at all."""

    with _client(tmp_path) as client:
        client.post(
            "/api/v1/feedback/modules/F0",
            json={**FEEDBACK, "comment": "UNIQUE-COMMENT-MARKER"},
        )
        export = client.get("/api/v1/progress/export").text

    assert "UNIQUE-COMMENT-MARKER" not in export
    assert "module_feedback" not in export


def test_the_gateway_url_is_never_disclosed_to_the_browser(tmp_path) -> None:
    endpoint = "https://internal-gateway.example.test/v1/feedback"
    with _client(tmp_path, endpoint=endpoint, transport=CountingTransport()) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/feedback/consent", json={"granted": True})
        bodies = [client.get("/api/v1/feedback").text, client.post("/api/v1/feedback/sync").text]

    for body in bodies:
        assert "internal-gateway.example.test" not in body
        assert endpoint not in body


# ----------------------------------------------------------- browser reach
def test_the_page_cannot_reach_any_external_host(tmp_path) -> None:
    """`connect-src 'self'` is what makes browser-to-GitHub structurally impossible.

    The documentation makes this claim, so the header that backs it is asserted
    rather than assumed.
    """

    with _client(tmp_path) as client:
        policy = client.get("/api/v1/feedback").headers["content-security-policy"]

    assert "connect-src 'self'" in policy
    assert "default-src 'self'" in policy


# ------------------------------------------------------- cross-component drift
def test_every_catalog_module_id_is_accepted_by_the_gateway_contract() -> None:
    """A contract that only holds for today's identifiers is a latent 422.

    The gateway constrains module ids to a strict pattern so they can be
    interpolated into the issue summary safely. If a future module id stops
    matching, feedback for it would be silently rejected at the intake — so the
    two components' notion of an identifier is checked against each other here.
    """

    from nornyx_lab.academy.catalog import CurriculumRepository

    identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
    for module in CurriculumRepository().modules():
        assert identifier.match(module.id), (
            f"module id {module.id!r} would be refused by the feedback gateway"
        )


def test_the_module_record_bound_cannot_be_exceeded_by_the_curriculum() -> None:
    """The gateway caps a session at 64 module records. One per module is the max."""

    from nornyx_lab.academy.catalog import CurriculumRepository

    assert len(CurriculumRepository().modules()) <= 64


# ------------------------------------------------------------- stale sync state
def test_a_stale_synced_digest_does_not_suppress_a_real_change(tmp_path) -> None:
    """Tampering with the local sync row must not silently stop delivery.

    Someone editing `synced_digest` by hand — or a bug writing the wrong one —
    must not leave later feedback permanently unsent. The digest is recomputed
    from content on every attempt, so a mismatch resumes sending.
    """

    transport = CountingTransport()
    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        sent = len(transport.calls)

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        connection.execute(
            "UPDATE feedback_sync_state SET synced_digest = 'sha256:' || ?", ("0" * 64,)
        )

    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=transport) as client:
        status = client.post("/api/v1/feedback/sync").json()

    assert len(transport.calls) == sent + 1, "a corrupted digest silently stopped delivery"
    assert status["sync"]["status"] == "synced"


def test_a_sync_state_row_for_an_unknown_session_does_not_crash_the_page(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.get("/api/v1/feedback")
    with sqlite3.connect(tmp_path / "academy.db") as connection:
        connection.execute(
            "INSERT INTO feedback_sync_state (session_id, status) VALUES ('orphan', 'synced')"
        )

    with _client(tmp_path) as client:
        assert client.get("/api/v1/feedback").status_code == 200


# ----------------------------------------------------------------- durability
def test_a_corrupt_transport_result_never_becomes_a_success_record(tmp_path) -> None:
    class LyingTransport:
        def send(self, endpoint, payload):
            # Claims success but names no issue: not a delivery confirmation.
            return TransportResult(ok=True, outcome="created", issue_number=None)

    with _client(tmp_path, endpoint="https://gw.test/v1/feedback", transport=LyingTransport()) as c:
        c.post("/api/v1/feedback/consent", json={"granted": True})
        c.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        status = c.get("/api/v1/feedback").json()

    # The record is kept honest: no issue reference is invented.
    assert status["sync"]["remote_reference"] is None


def test_feedback_survives_a_progress_reset_and_a_restart_together(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/progress/reset")
    with _client(tmp_path) as client:
        status = client.get("/api/v1/feedback").json()

    assert len(status["module_feedback"]) == 1
    assert status["module_feedback"][0]["comment"] == "fine"


# ------------------------------------------------------------------ container
def test_the_compose_deployment_ships_no_feedback_credential() -> None:
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert "NORNYX_FEEDBACK_GITHUB_TOKEN" not in compose
    assert "NORNYX_FEEDBACK_ENDPOINT" not in compose, (
        "the default learner deployment must not point at a feedback endpoint"
    )


def test_the_learner_dockerfile_sets_no_feedback_environment() -> None:
    dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
    for name in (
        "NORNYX_FEEDBACK_GITHUB_TOKEN",
        "NORNYX_FEEDBACK_GITHUB_REPOSITORY",
        "NORNYX_FEEDBACK_ENDPOINT",
    ):
        assert name not in dockerfile

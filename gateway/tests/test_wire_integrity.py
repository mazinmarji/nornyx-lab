"""Type-shaped JSON is not the same as coherent JSON.

A payload can satisfy every field's type and still describe something that is
not true of itself — a session declaring three module records while carrying
one. Rendered, the summary line and the table beneath it would contradict each
other, and a maintainer reading the issue has no way to tell which is the
learner's actual feedback.

The same category of problem is the reason strict typing matters here: silent
coercion changes values, and the gateway digests what it parsed, so a coerced
value is a value the sender never digested.

Also asserted here: the course-level record carries no module-shaped
placeholders. Research data must not contain values that look like observations
and are not.
"""

from __future__ import annotations

import pytest
from conftest import digest_of, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.models import CourseAcademyContext, FeedbackPayload


def _post(config, sink, payload):
    with TestClient(create_app(config=config, sink=sink)) as api:
        return api.post("/v1/feedback", json=payload)


# --------------------------------------------------------------- cross-field
@pytest.mark.parametrize("declared", [0, 2, 5, 64])
def test_a_module_count_that_does_not_match_the_records_is_refused(config, sink, declared) -> None:
    payload = make_payload()  # carries exactly one module record
    payload["session"]["module_record_count"] = declared
    payload["sync"]["payload_digest"] = digest_of(payload)

    response = _post(config, sink, payload)

    assert response.status_code == 422, f"declared {declared} against one record"
    assert sink.calls == []


def test_a_course_count_claiming_a_record_that_is_absent_is_refused(config, sink) -> None:
    payload = make_payload(with_course=False)
    payload["session"]["course_record_count"] = 1
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 422
    assert sink.calls == []


def test_a_course_count_of_zero_while_carrying_one_is_refused(config, sink) -> None:
    payload = make_payload(with_course=True)
    payload["session"]["course_record_count"] = 0
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 422
    assert sink.calls == []


def test_matching_counts_are_accepted(config, sink) -> None:
    """Positive control, both with and without a course record."""

    assert _post(config, sink, make_payload(with_course=True)).status_code == 202
    other = make_payload(session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", with_course=False)
    assert _post(config, sink, other).status_code == 202


def test_the_rendered_summary_cannot_disagree_with_the_table(config, sink) -> None:
    """Why the count check exists, stated as the rendered outcome."""

    assert _post(config, sink, make_payload()).status_code == 202
    body = sink.issues[1]["body"]

    assert "- Module records: 1" in body
    assert body.count("| `F0` |") == 1


# ------------------------------------------------------------------ coercion
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("module_feedback", 0, "perception", "clarity"), "4"),
        (("module_feedback", 0, "perception", "clarity"), 4.0),
        (("module_feedback", 0, "academy_context", "assessment_passed"), 1),
        (("module_feedback", 0, "academy_context", "assessment_passed"), "true"),
        (("module_feedback", 0, "academy_context", "assessment_attempts"), "1"),
        (("module_feedback", 0, "record_id"), "1"),
        (("session", "module_record_count"), "1"),
        (("module_feedback", 0, "perception", "comment"), 42),
        (("schema_id",), 1),
    ],
)
def test_values_of_the_wrong_type_are_refused_rather_than_coerced(
    config, sink, path, value
) -> None:
    """Coercion would rewrite the payload the sender digested."""

    payload = make_payload()
    target = payload
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    response = _post(config, sink, payload)

    assert response.status_code == 422, f"{path} accepted {value!r}"
    assert sink.calls == []


def test_an_integer_score_is_still_accepted_as_a_number(config, sink) -> None:
    """The one coercion kept: JSON has a single number type.

    Refusing ``0`` for a score would be refusing valid JSON that means exactly
    what it appears to mean.
    """

    payload = make_payload()
    payload["module_feedback"][0]["academy_context"]["assessment_score"] = 1
    payload["sync"]["payload_digest"] = digest_of(payload)

    # The digest is computed over the integer the sender actually sent, and the
    # gateway recomputes over the parsed float — so this is refused for digest
    # reasons, not type reasons. What matters is that the *type* is accepted.
    assert (
        FeedbackPayload.model_validate(payload).module_feedback[0].academy_context.assessment_score
        == 1.0
    )


# -------------------------------------------------------- honest course context
def test_the_course_context_has_no_module_shaped_fields() -> None:
    """A placeholder in a research record is indistinguishable from an observation."""

    fields = set(CourseAcademyContext.model_fields)

    assert fields == {
        "total_assessment_attempts",
        "competence_revision",
        "learning_path_id",
        "session_elapsed_seconds",
    }
    for fabricated in ("module_status", "assessment_score", "assessment_passed"):
        assert fabricated not in fields, (
            f"course context still carries {fabricated}, which has no referent at course level"
        )


def test_a_course_record_carrying_a_module_status_is_refused(config, sink) -> None:
    """The old shape must not be quietly accepted alongside the new one."""

    payload = make_payload()
    payload["course_feedback"]["academy_context"]["module_status"] = "not_started"
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 422
    assert sink.calls == []


def test_the_rendered_course_section_makes_no_module_claim(config, sink) -> None:
    assert _post(config, sink, make_payload()).status_code == 202
    body = sink.issues[1]["body"]

    course = body.split("### Course feedback")[1].split("###")[0]
    for fabricated in ("not_started", "module_status", "Passed"):
        assert fabricated not in course, f"the course section states {fabricated}"


def test_the_module_context_still_carries_its_module_fields(config, sink) -> None:
    """Positive control: removing the placeholder must not remove real provenance."""

    assert _post(config, sink, make_payload()).status_code == 202
    body = sink.issues[1]["body"]

    assert "| `F0` |" in body
    assert "| 1.00 | yes |" in body


# ------------------------------------------------------------------ structure
def test_unknown_fields_anywhere_in_the_tree_are_refused(config, sink) -> None:
    for path in (
        ("session",),
        ("runtime",),
        ("sync",),
        ("module_feedback", 0),
        ("module_feedback", 0, "perception"),
        ("module_feedback", 0, "academy_context"),
        ("course_feedback", "perception"),
        ("course_feedback", "academy_context"),
    ):
        payload = make_payload()
        target = payload
        for step in path:
            target = target[step]
        target["unexpected"] = "value"
        payload["sync"]["payload_digest"] = digest_of(payload)

        assert _post(config, sink, payload).status_code == 422, path
    assert sink.calls == []

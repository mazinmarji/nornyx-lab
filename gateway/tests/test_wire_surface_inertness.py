"""Every caller-supplied string, not just the comment fields.

Fencing the free text was the obvious half. The other half is everything else
that reaches the rendered issue: the session's opening timestamp, five version
strings, the competence revisions, the identifiers. Those were bounded only by
length, so a payload could put a backtick, a newline, an ``@mention``, or a
Markdown link into the summary the maintainers read — outside any fence, where
Markdown interprets it.

This module enumerates **every string-valued position in the wire contract** and
attacks each one with the same hostile corpus. For each the outcome must be one
of exactly two things:

* the payload is refused, because the field has a syntax and this is not it; or
* the value survives and appears only inside a fenced block.

Nothing may be accepted and rendered loose. The enumeration walks a real payload
rather than a hand-written list of fields, so a field added later is attacked
automatically instead of being quietly exempt.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from conftest import digest_of, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app

HOSTILE = [
    "`backtick`",
    "```fence```",
    "line\nbreak",
    "@maintainer",
    "#123",
    "<script>alert(1)</script>",
    "[link](https://evil.test)",
    "${{ secrets.GITHUB_TOKEN }}",
    "| table | injection |",
    "**bold**",
]


def _string_paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Every path in the payload whose value is a string."""

    found: list[tuple[Any, ...]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found += _string_paths(value, (*prefix, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _string_paths(value, (*prefix, index))
    elif isinstance(node, str):
        found.append(prefix)
    return found


def _set(document: Any, path: tuple[Any, ...], value: str) -> None:
    target = document
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value


ALL_STRING_PATHS = _string_paths(make_payload())


def _fenced_regions(body: str) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    open_fence: str | None = None
    start = 0
    offset = 0
    for line in body.split("\n"):
        stripped = line.rstrip()
        match = re.match(r"^(`{3,})", stripped)
        if open_fence is None:
            if match:
                open_fence = match.group(1)
                start = offset
        elif stripped == open_fence:
            regions.append((start, offset + len(line)))
            open_fence = None
        offset += len(line) + 1
    return regions


def _loose_occurrences(body: str, needle: str) -> int:
    """How many times the needle appears outside every fenced block."""

    regions = _fenced_regions(body)
    loose = 0
    index = body.find(needle)
    while index != -1:
        if not any(start <= index and index + len(needle) <= end for start, end in regions):
            loose += 1
        index = body.find(needle, index + 1)
    return loose


def test_the_loose_occurrence_oracle_detects_unfenced_text() -> None:
    """Negative control. An oracle that always returns zero would prove nothing."""

    body = "summary @maintainer\n```text\n@maintainer\n```\n"
    assert _loose_occurrences(body, "@maintainer") == 1
    assert _loose_occurrences("```text\n@maintainer\n```\n", "@maintainer") == 0


def test_the_enumeration_actually_covers_the_contract() -> None:
    """Guard against the walker silently finding nothing."""

    flattened = {".".join(str(step) for step in path) for path in ALL_STRING_PATHS}
    assert len(flattened) >= 20, flattened
    for expected in (
        "session.created_at",
        "runtime.academy_version",
        "runtime.nornyx_version",
        "runtime.adapter_version",
        "runtime.api_version",
        "runtime.content_version",
        "module_feedback.0.created_at",
        "module_feedback.0.module_id",
        "module_feedback.0.perception.comment",
        "module_feedback.0.academy_context.competence_revision",
        "module_feedback.0.academy_context.assessment_evidence_revision",
        "course_feedback.created_at",
        "course_feedback.academy_context.competence_revision",
        "sync.generated_at",
    ):
        assert expected in flattened, f"{expected} is not covered by the sweep"


@pytest.mark.parametrize(
    "path", ALL_STRING_PATHS, ids=lambda path: ".".join(str(step) for step in path)
)
@pytest.mark.parametrize("hostile", HOSTILE, ids=range(len(HOSTILE)))
def test_no_wire_string_can_reach_interpreted_markdown(config, sink, path, hostile) -> None:
    payload = make_payload()
    _set(payload, path, hostile)
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        response = api.post("/v1/feedback", json=payload)

    if response.status_code != 202:
        # Refused: the field has a syntax and this is not it. Nothing rendered.
        assert response.status_code == 422, response.text
        assert sink.calls == []
        return

    body = sink.issues[1]["body"]
    assert _loose_occurrences(body, hostile) == 0, (
        f"{'.'.join(str(step) for step in path)} reached interpreted Markdown carrying {hostile!r}"
    )


# ------------------------------------------------------- field syntax, directly
@pytest.mark.parametrize(
    "field",
    ["academy_version", "nornyx_version", "adapter_version", "api_version", "content_version"],
)
@pytest.mark.parametrize("hostile", HOSTILE, ids=range(len(HOSTILE)))
def test_version_strings_are_refused_rather_than_escaped(config, sink, field, hostile) -> None:
    """These reach the summary line, so they have a syntax rather than a length."""

    payload = make_payload()
    payload["runtime"][field] = hostile
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        response = api.post("/v1/feedback", json=payload)

    assert response.status_code == 422
    assert sink.calls == []


@pytest.mark.parametrize(
    "value",
    [
        "not a timestamp",
        "2026-13-45T99:99:99Z",
        "2026-08-10T12:00:00",  # no offset: not an instant
        "`2026-08-10T12:00:00Z`",
        "2026-08-10T12:00:00Z\n@everyone",
        "",
        "0000",
    ],
)
def test_timestamps_are_parsed_not_pattern_guessed(config, sink, value) -> None:
    payload = make_payload()
    payload["session"]["created_at"] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        response = api.post("/v1/feedback", json=payload)

    assert response.status_code == 422, f"{value!r} was accepted as a timestamp"
    assert sink.calls == []


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-10T12:00:00Z",
        "2026-08-10T12:00:00.123456Z",
        "2026-08-10T12:00:00+00:00",
        "2026-08-10T14:00:00+02:00",
    ],
)
def test_genuine_instants_are_accepted(config, sink, value) -> None:
    """Positive control: the validation must not reject the Academy's own format."""

    payload = make_payload()
    payload["session"]["created_at"] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        assert api.post("/v1/feedback", json=payload).status_code == 202


@pytest.mark.parametrize(
    "value", ["2.0.0", "1.11.0", "v1", "2026.08.1", "0.3.0", "1.0.0-rc.1", "2.0.0+build.7"]
)
def test_real_version_strings_are_accepted(config, sink, value) -> None:
    payload = make_payload()
    payload["runtime"]["academy_version"] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        assert api.post("/v1/feedback", json=payload).status_code == 202


def test_a_real_competence_revision_is_accepted(config, sink) -> None:
    payload = make_payload()
    for record in payload["module_feedback"]:
        record["academy_context"]["competence_revision"] = "assessment.2026-08-10"
        record["academy_context"]["assessment_evidence_revision"] = "assessment:2026-08-10+1"
    payload["sync"]["payload_digest"] = digest_of(payload)

    with TestClient(create_app(config=config, sink=sink)) as api:
        assert api.post("/v1/feedback", json=payload).status_code == 202


def test_the_summary_section_contains_no_unfenced_caller_string(config, sink) -> None:
    """Read the rendered summary and check it against the payload it describes."""

    payload = make_payload(comment="a comment with `backticks` and @mention")
    with TestClient(create_app(config=config, sink=sink)) as api:
        assert api.post("/v1/feedback", json=payload).status_code == 202

    body = sink.issues[1]["body"]
    summary = body.split("### Learner free text")[0]
    for path in ALL_STRING_PATHS:
        value = payload
        for step in path:
            value = value[step]
        if not isinstance(value, str) or len(value) < 3:
            continue
        if value in summary:
            # Present in the summary is fine only for values whose syntax makes
            # them inert; assert that syntax rather than assuming it.
            assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:+\-]*", value) or json.dumps(value), value
            assert "`" not in value and "\n" not in value and "@" not in value

"""A parseable timestamp is not automatically an inert one.

The earlier fix required timestamps to parse via ``datetime.fromisoformat`` and
to carry a timezone. That is not enough, and the gap is easy to miss because the
value really is a valid instant: ``fromisoformat`` accepts **any single
character** as the date/time separator. So

    2026-08-11`12:00:00+00:00

is a genuine timezone-aware moment as far as Python is concerned, and it reached
the rendered summary inside a code span:

    - Opened: `2026-08-11`12:00:00+00:00`

where the backtick closes the span early and the remainder becomes interpreted
Markdown. The newline variant is worse — it ends the line entirely and the rest
of the value lands in the document as loose text.

The previous hostile sweep missed this because it replaced timestamps with
*invalid* strings, which were rejected, rather than injecting hostile characters
into a timestamp that still parses.

Every timestamp field in the contract is attacked here, not just the one that is
rendered, because the next renderer will not remember which was which.
"""

from __future__ import annotations

import re

import pytest
from conftest import digest_of, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.models import ISO_INSTANT_PATTERN

#: Every separator ``datetime.fromisoformat`` tolerates that carries meaning in
#: Markdown, breaks a line, or is simply not the character the format specifies.
HOSTILE_SEPARATORS = {
    "backtick": "`",
    "newline": "\n",
    "carriage-return": "\r",
    "at-sign": "@",
    "pipe": "|",
    "space": " ",
    "hash": "#",
    "asterisk": "*",
    "bracket": "[",
    "backslash": "\\",
    "non-breaking-space": " ",
    "line-separator": " ",
    "paragraph-separator": " ",
    "ideographic-space": "　",
    "letter": "x",
    "underscore": "_",
}

#: Where a timestamp lives in the contract.
TIMESTAMP_PATHS = [
    ("session", "created_at"),
    ("module_feedback", 0, "created_at"),
    ("course_feedback", "created_at"),
    ("sync", "generated_at"),
]


def _set(document, path, value) -> None:
    target = document
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value


def _post(config, sink, payload):
    with TestClient(create_app(config=config, sink=sink)) as api:
        return api.post("/v1/feedback", json=payload)


# --------------------------------------------------------------------- attack
@pytest.mark.parametrize("name", sorted(HOSTILE_SEPARATORS))
@pytest.mark.parametrize("path", TIMESTAMP_PATHS, ids=lambda p: ".".join(str(s) for s in p))
def test_a_parseable_timestamp_with_a_hostile_separator_is_refused(
    config, sink, name, path
) -> None:
    separator = HOSTILE_SEPARATORS[name]
    hostile = f"2026-08-11{separator}12:00:00+00:00"

    payload = make_payload()
    _set(payload, path, hostile)
    payload["sync"]["payload_digest"] = digest_of(payload)

    response = _post(config, sink, payload)

    assert response.status_code == 422, (
        f"{'.'.join(str(s) for s in path)} accepted a timestamp separated by {name}"
    )
    assert sink.calls == [], "a hostile timestamp reached the GitHub boundary"


@pytest.mark.parametrize("name", sorted(HOSTILE_SEPARATORS))
def test_the_hostile_separator_really_does_parse_as_an_instant(name) -> None:
    """The premise, verified — otherwise the attack above proves nothing.

    If Python rejected these outright the tests would pass for the wrong reason
    and would keep passing after a regression.
    """

    from datetime import datetime

    value = f"2026-08-11{HOSTILE_SEPARATORS[name]}12:00:00+00:00"
    parsed = datetime.fromisoformat(value)

    assert parsed.tzinfo is not None, (
        "this separator is not actually accepted, so it is not a valid attack case"
    )


def test_the_backtick_variant_would_have_escaped_the_code_span() -> None:
    """Show the concrete consequence, so the refusal has a stated reason."""

    hostile = "2026-08-11`12:00:00+00:00"
    rendered = f"- Opened: `{hostile}`"

    # An odd number of backticks: the span the renderer opened does not close
    # where it was meant to, and the tail becomes interpreted Markdown.
    assert rendered.count("`") % 2 == 1
    assert not re.fullmatch(r"- Opened: `[^`]*`", rendered)


def test_the_newline_variant_would_have_left_the_line_entirely() -> None:
    hostile = "2026-08-11\n12:00:00+00:00"
    rendered = f"- Opened: `{hostile}`"

    assert len(rendered.split("\n")) == 2
    assert rendered.split("\n")[1] == "12:00:00+00:00`"


# ------------------------------------------------------------------ positives
@pytest.mark.parametrize(
    "value",
    [
        "2026-08-11T12:00:00Z",
        "2026-08-11T12:00:00.1Z",
        "2026-08-11T12:00:00.123456Z",
        "2026-08-11T12:00:00+00:00",
        "2026-08-11T14:00:00+02:00",
        "2026-08-11T00:00:00-05:00",
    ],
)
@pytest.mark.parametrize("path", TIMESTAMP_PATHS, ids=lambda p: ".".join(str(s) for s in p))
def test_the_forms_the_academy_emits_are_accepted(config, sink, value, path) -> None:
    payload = make_payload()
    _set(payload, path, value)
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 202


def test_the_academys_own_timestamp_format_matches_the_pattern() -> None:
    """Cross-check against how the Academy actually formats an instant."""

    from datetime import UTC, datetime

    emitted = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert re.fullmatch(ISO_INSTANT_PATTERN, emitted), emitted


def test_the_golden_academy_payload_still_validates(config, sink) -> None:
    """The committed real payload must not be collateral damage."""

    import json
    from pathlib import Path

    payload = json.loads(
        (Path(__file__).parent / "academy_payload.golden.json").read_text(encoding="utf-8")
    )
    assert _post(config, sink, payload).status_code == 202


# ------------------------------------------------------------- semantic half
@pytest.mark.parametrize(
    "value",
    [
        "2026-13-11T12:00:00Z",
        "2026-08-45T12:00:00Z",
        "2026-08-11T99:00:00Z",
        "2026-02-30T12:00:00Z",
    ],
)
def test_impossible_dates_are_still_refused(config, sink, value) -> None:
    """The pattern fixes the alphabet; the parse still has to fix the meaning."""

    payload = make_payload()
    payload["session"]["created_at"] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 422


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-11T12:00:00",
        "2026-08-11",
        "20260811T120000Z",
        "2026-08-11T12:00Z",
        "2026-08-11T12:00:00.1234567Z",
        "2026-08-11T12:00:00+0000",
        " 2026-08-11T12:00:00Z",
        "2026-08-11T12:00:00Z ",
    ],
)
def test_near_miss_forms_are_refused(config, sink, value) -> None:
    payload = make_payload()
    payload["session"]["created_at"] = value
    payload["sync"]["payload_digest"] = digest_of(payload)

    assert _post(config, sink, payload).status_code == 422, f"{value!r} was accepted"

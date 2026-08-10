"""Turn a validated payload into a GitHub issue title and body.

The whole security argument for this file is one sentence:

    **no learner-authored character is ever emitted as Markdown.**

Learner-authored strings — the free-text comments — are emitted only inside a
fenced code block whose fence is computed to be longer than the longest run of
backticks in the text itself, so the text cannot close its own fence. GitHub
does not parse mentions, issue references, or any other Markdown inside a fenced
block, which is what keeps `@maintainer`, `#123`, `<script>`, and Actions-looking
syntax inert.

Everything outside a fence is generated here from values Pydantic has already
constrained to enums, bounded integers, or a strict identifier pattern. The
title is derived from the session UUID alone. Labels, repository, and issue
state come from deployment configuration. There is therefore no field a learner
can write that reaches a position where it could be interpreted.

This is a *rendering* boundary, not a sanitiser. Nothing is stripped from the
learner's words except carriage returns and C0 control characters that no
terminal-free reader would see anyway; the text is preserved verbatim so the
feedback stays usable as research material.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import FeedbackPayload

#: Lets a later synchronisation find the issue that already represents a session
#: even when the gateway's own store has been lost. Written as an HTML comment so
#: it is invisible in the rendered issue but present in the raw body.
MARKER_PREFIX = "nornyx-feedback-session:"

#: C0 controls other than tab and newline. Feedback typed into a textarea should
#: not contain these; if it does they carry no meaning for a human reader and
#: removing them keeps the body a clean text document.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BACKTICK_RUN = re.compile(r"`+")


def session_marker(session_id: str) -> str:
    return f"<!-- {MARKER_PREFIX} {session_id} -->"


def issue_title(session_id: str) -> str:
    """A deterministic, learner-independent title.

    Derived only from the session UUID, so the same session always produces the
    same title and recovery can match on it exactly. Learner text never reaches
    this string.
    """

    return f"[Learner Feedback] Session {session_id[:8]}"


def normalise(text: str) -> str:
    """Remove carriage returns and unrenderable control characters. Nothing else."""

    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def fenced(text: str, *, language: str = "text") -> str:
    """Wrap arbitrary text in a code fence that the text cannot escape.

    The fence is one backtick longer than the longest backtick run inside the
    content, with a floor of three. A body containing ```` ``` ```` therefore gets a
    four-backtick fence, and no line of the content can ever equal the closing
    delimiter.
    """

    body = normalise(text)
    longest = max((len(match.group()) for match in _BACKTICK_RUN.finditer(body)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{body}\n{fence}"


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _score(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.2f}"


def payload_document(payload: FeedbackPayload) -> dict[str, Any]:
    """The machine-readable object embedded in the issue body.

    This is the payload exactly as received, minus nothing and plus nothing, so
    a maintainer reading the issue sees what the installation actually sent.
    """

    return payload.model_dump(mode="json", exclude_none=False)


def _module_rows(payload: FeedbackPayload) -> list[str]:
    rows = [
        "| Module | Clarity | Confidence | Difficulty | Self-assessment | Assessment | Passed |",
        "|---|---:|---:|---|---|---:|---|",
    ]
    for record in payload.module_feedback:
        perception = record.perception
        context = record.academy_context
        rows.append(
            f"| `{record.module_id}` | {perception.clarity} | {perception.confidence} "
            f"| {perception.difficulty} | {perception.self_assessment} "
            f"| {_score(context.assessment_score)} | {_yes_no(context.assessment_passed)} |"
        )
    return rows


def _comment_sections(payload: FeedbackPayload) -> list[str]:
    """Every learner-authored string, each inside its own fence."""

    sections: list[str] = []
    for record in payload.module_feedback:
        comment = (record.perception.comment or "").strip()
        if comment:
            sections.append(f"**Module `{record.module_id}` — what was confusing or missing**")
            sections.append(fenced(comment))
    course = payload.course_feedback
    if course is not None:
        for label, value in (
            ("Missing topic", course.perception.missing_topic),
            ("Overall comments", course.perception.comments),
        ):
            text = (value or "").strip()
            if text:
                sections.append(f"**{label}**")
                sections.append(fenced(text))
    return sections


def issue_body(payload: FeedbackPayload) -> str:
    """Render the complete issue body.

    Two parts, in the order a human wants them: a readable summary built only
    from constrained values, then the exact payload as JSON for analysis.
    """

    session = payload.session
    runtime = payload.runtime
    parts: list[str] = [
        session_marker(session.session_id),
        "",
        "## Learner feedback session",
        "",
        "Subjective learner perception collected by Nornyx Academy and forwarded with the "
        "learner's explicit consent. **This is research instrumentation, not evidence of "
        "learner competence, and not a measurement of educational effectiveness.**",
        "",
        f"- Session: `{session.session_id}`",
        f"- Opened: `{session.created_at}`",
        f"- Module records: {session.module_record_count}",
        f"- Course records: {session.course_record_count}",
        "",
        "### Runtime",
        "",
        f"- Academy `{runtime.academy_version}` · Nornyx `{runtime.nornyx_version}` "
        f"· adapters `{runtime.adapter_version}` · API `{runtime.api_version}` "
        f"· content `{runtime.content_version}`",
        "",
    ]

    if payload.module_feedback:
        parts += ["### Module ratings", "", *_module_rows(payload), ""]

    if payload.course_feedback is not None:
        course = payload.course_feedback.perception
        parts += [
            "### Course feedback",
            "",
            f"- Overall clarity: {course.overall_clarity}/5",
            f"- Progression: {course.progression}/5",
            f"- Practical usefulness: {course.usefulness}/5",
            f"- Final confidence: {course.final_confidence}/5",
            f"- Overall difficulty: {course.overall_difficulty}",
            f"- Would recommend: {course.recommend}",
            f"- Most helpful module: "
            f"{f'`{course.most_helpful_module}`' if course.most_helpful_module else 'not stated'}",
            f"- Most confusing module: "
            f"{f'`{course.most_confusing_module}`' if course.most_confusing_module else 'not stated'}",
            "",
        ]

    comments = _comment_sections(payload)
    if comments:
        parts += [
            "### Learner free text",
            "",
            "Quoted verbatim inside code fences. It is learner-authored, unverified, and "
            "deliberately not rendered as Markdown.",
            "",
            *comments,
            "",
        ]

    document = json.dumps(payload_document(payload), indent=2, sort_keys=True, ensure_ascii=False)
    parts += [
        "### Machine-readable payload",
        "",
        fenced(document, language="json"),
        "",
        f"Digest: `{payload.sync.payload_digest}`",
        "",
        "> Assessment context in this payload is generated by the learner's own academy "
        "> installation. It is self-reported by that installation and is not independently "
        "> verified by this intake.",
    ]
    return "\n".join(parts)


__all__ = [
    "MARKER_PREFIX",
    "fenced",
    "issue_body",
    "issue_title",
    "normalise",
    "payload_document",
    "session_marker",
]

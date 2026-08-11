"""The versioned wire contract, validated as hostile external input.

This service is reachable from the open internet and has no authentication, so
nothing that arrives here is trusted. Every model forbids unknown fields, every
number has a range, every category is an enum, and every free-text field has a
hard length bound. A payload that does not satisfy the contract is rejected —
it is never repaired, truncated into validity, or partially accepted.

The academy context carried in these models is Academy-generated evidence about
the learner's own installation. It is recorded because it is the only way to
read a rating in context; it is **not** independent ground truth, and a modified
client can state whatever it likes here. Analysis must treat it accordingly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .config import SCHEMA_ID

#: Identifiers the academy uses for modules and paths. Constrained rather than
#: sanitised: an id outside this set is a malformed payload, and accepting one
#: would put attacker-chosen characters into the rendered issue summary.
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")]

#: A hyphenated lowercase UUID. Validated as a string rather than parsed into a
#: ``UUID`` so the exact text the client sent is what gets stored and matched.
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
SessionId = Annotated[str, StringConstraints(pattern=UUID_PATTERN)]


def _instant(value: str) -> str:
    """Require an actual timezone-aware ISO-8601 instant, not a timestamp-shaped string.

    Checking length or "looks like a date" leaves a field that reaches the
    rendered issue summary accepting arbitrary text. Parsing it is both the
    stronger validation and the more honest one: a timestamp that cannot be
    read as a moment in time is not a timestamp.
    """

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("must carry a timezone offset")
    return value


#: A real instant. Bounded first so a pathological string never reaches the parser.
Timestamp = Annotated[str, StringConstraints(min_length=4, max_length=40), AfterValidator(_instant)]

#: Version and revision identifiers reach the rendered summary, so their syntax
#: is constrained to characters that carry no meaning in Markdown. This is not
#: sanitisation — a value outside the set is a malformed payload and is refused.
Version = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")]
Revision = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

Comment = Annotated[str, StringConstraints(max_length=2000)]
LongComment = Annotated[str, StringConstraints(max_length=4000)]

Rating = Annotated[int, Field(ge=1, le=5)]
Difficulty = Literal["too_easy", "right_level", "too_hard"]
SelfAssessment = Literal["understood", "partly_understood", "still_confused"]
Recommend = Literal["yes", "maybe", "no"]

#: Bounds on collection sizes. The academy ships 31 modules, so a session that
#: claims hundreds of module records is not a learner.
MAX_MODULE_RECORDS = 64


class Wire(BaseModel):
    """Strict in both directions.

    ``extra="forbid"`` refuses fields nobody declared; ``strict=True`` refuses
    values of the wrong type rather than quietly coercing them. Coercion matters
    here beyond tidiness: the gateway recomputes the payload digest from what it
    parsed, so a silently rewritten value would produce a digest that no longer
    matches the sender's — and the honest answer to "this is not the payload you
    digested" is refusal, not repair.

    Pydantic's one strict-mode concession, accepting an integer for a float, is
    kept: JSON has a single number type and refusing ``0`` for a score would be
    refusing valid JSON.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


class AcademyContext(Wire):
    """What the learner's installation says was true when a module rating was given.

    ``assessment_passed`` has three meanings, not two. ``true`` and ``false``
    are judgements under semantics that currently apply; ``null`` means the
    installation held no admissible evidence — for instance because the pass
    was earned under a competence revision that has since been superseded.
    Analysis must not read ``null`` as ``false``.

    ``competence_revision`` is what an assessment means today;
    ``assessment_evidence_revision`` is what the reported evidence was actually
    earned under. They differ only when a prior revision was explicitly declared
    compatible.
    """

    module_status: Literal["not_started", "in_progress", "needs_review", "complete"]
    assessment_score: float | None = Field(default=None, ge=0, le=1)
    assessment_passed: bool | None = None
    assessment_attempts: int = Field(ge=0, le=10_000)
    competence_revision: Revision | None = None
    assessment_evidence_revision: Revision | None = None
    learning_path_id: Identifier | None = None
    session_elapsed_seconds: int | None = Field(default=None, ge=0, le=60 * 60 * 24 * 30)


class CourseAcademyContext(Wire):
    """Provenance for a course-level rating.

    Deliberately carries no module status, score, or pass/fail. Course feedback
    is about the whole curriculum, so those fields would have no referent, and a
    placeholder in a research record is indistinguishable from an observation.
    """

    total_assessment_attempts: int = Field(ge=0, le=1_000_000)
    competence_revision: Revision | None = None
    learning_path_id: Identifier | None = None
    session_elapsed_seconds: int | None = Field(default=None, ge=0, le=60 * 60 * 24 * 30)


class ModulePerception(Wire):
    clarity: Rating
    confidence: Rating
    difficulty: Difficulty
    self_assessment: SelfAssessment
    comment: Comment | None = None


class ModuleFeedbackRecord(Wire):
    record_id: int = Field(ge=1)
    module_id: Identifier
    created_at: Timestamp
    perception: ModulePerception
    academy_context: AcademyContext


class CoursePerception(Wire):
    overall_clarity: Rating
    progression: Rating
    usefulness: Rating
    final_confidence: Rating
    overall_difficulty: Difficulty
    recommend: Recommend
    most_helpful_module: Identifier | None = None
    most_confusing_module: Identifier | None = None
    missing_topic: Comment | None = None
    comments: LongComment | None = None


class CourseFeedbackRecord(Wire):
    record_id: int = Field(ge=1)
    created_at: Timestamp
    perception: CoursePerception
    academy_context: CourseAcademyContext


class SessionInfo(Wire):
    session_id: SessionId
    created_at: Timestamp
    module_record_count: int = Field(ge=0, le=MAX_MODULE_RECORDS)
    course_record_count: int = Field(ge=0, le=1)


class RuntimeInfo(Wire):
    academy_version: Version
    nornyx_version: Version
    adapter_version: Version
    api_version: Version
    content_version: Version


class SyncInfo(Wire):
    payload_digest: Digest
    generated_at: Timestamp


class FeedbackPayload(Wire):
    """One feedback session, in full, as the academy currently holds it.

    Every synchronisation sends the whole session rather than a delta. That is
    what makes the operation idempotent: the same session always renders to the
    same issue body, so a retry is indistinguishable from the first attempt and
    a restart cannot produce a partial record.
    """

    schema_id: Literal[SCHEMA_ID]
    session: SessionInfo
    runtime: RuntimeInfo
    module_feedback: list[ModuleFeedbackRecord] = Field(
        default_factory=list, max_length=MAX_MODULE_RECORDS
    )
    course_feedback: CourseFeedbackRecord | None = None
    sync: SyncInfo

    @model_validator(mode="after")
    def _counts_describe_the_contents(self) -> FeedbackPayload:
        """The declared counts must be true of the payload that carries them.

        Type-shaped JSON is not the same as coherent JSON. A session claiming
        three module records while carrying one is either a broken client or a
        deliberate one, and in the rendered issue the summary line would
        contradict the table beneath it. Refuse rather than pick a winner.
        """

        if self.session.module_record_count != len(self.module_feedback):
            raise ValueError(
                "session.module_record_count does not match the module_feedback entries"
            )
        expected_course = int(self.course_feedback is not None)
        if self.session.course_record_count != expected_course:
            raise ValueError(
                "session.course_record_count does not match the presence of course_feedback"
            )
        return self


class AcceptedResponse(Wire):
    """Deliberately minimal.

    The intake repository's name is **not** returned. A learner installation has
    no need for it, and if the maintainers configure a private intake repository
    its name should not be handed to every client that posts feedback.
    """

    status: Literal["created", "updated", "unchanged"]
    issue_number: int = Field(ge=1)
    destination_visibility: Literal["public", "private", "unknown"]
    schema_id: Literal[SCHEMA_ID] = SCHEMA_ID


class ErrorResponse(Wire):
    code: str
    message: str


class HealthResponse(Wire):
    status: Literal["ok"] = "ok"
    schema_id: Literal[SCHEMA_ID] = SCHEMA_ID
    #: Whether a GitHub repository *and* credential are both configured. The
    #: credential itself is never represented here in any form.
    github_configured: bool
    destination_visibility: Literal["public", "private", "unknown"]


__all__ = [
    "MAX_MODULE_RECORDS",
    "AcademyContext",
    "CourseAcademyContext",
    "AcceptedResponse",
    "CourseFeedbackRecord",
    "CoursePerception",
    "ErrorResponse",
    "FeedbackPayload",
    "HealthResponse",
    "ModuleFeedbackRecord",
    "ModulePerception",
    "RuntimeInfo",
    "SessionInfo",
    "SyncInfo",
]

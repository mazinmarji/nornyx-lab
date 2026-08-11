"""Local-first learner feedback: what the learner felt, kept apart from what they proved.

This module exists to collect *perception*. The academy already has a careful
model of what a learner has demonstrated, built on recorded executions, scored
assessments, and the competence revision each was earned under. Perception is a
different kind of thing entirely, and the single most important property of this
feature is that the two never mix:

    learner perception
        ≠ Academy assessment evidence
        ≠ learner-authored competence evidence
        ≠ external human-observation evidence

Nothing here is read by assessment scoring, module completion, concept mastery,
capstone eligibility, competence revision, or ``AdvancedStanding``. The
dependency arrow points one way only — feedback reads the learner record to
record *context*, and the learner record has never heard of feedback. That
direction is enforced by test, not by convention.

Three further commitments the implementation is shaped by:

* **The local write is the product.** A rating is saved to SQLite before any
  network call is considered, and no delivery failure can undo it. A learner
  with no internet loses nothing.
* **The browser supplies perception, the server supplies provenance.** Scores,
  statuses, versions, and competence revisions are read here at the moment the
  rating is stored. A modified client cannot author them.
* **Nothing leaves without explicit consent.** Consent is read from the
  database, never from the request that would be transmitted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .competence import CompetenceContract, EvidenceFamily
from .feedback_client import FeedbackTransport, TransportResult
from .progress import AdmissibleAssessment
from .schemas import (
    API_VERSION,
    CONSENT_DOCUMENT_VERSION,
    FEEDBACK_SCHEMA_ID,
    CourseFeedbackRecord,
    CourseFeedbackRequest,
    CourseFeedbackSummary,
    DestinationVisibility,
    FeedbackAcademyContext,
    FeedbackConsentState,
    FeedbackCourseContext,
    FeedbackDeletionResponse,
    FeedbackDifficulty,
    FeedbackRecommendation,
    FeedbackStatus,
    FeedbackSubmissionResponse,
    FeedbackSummary,
    FeedbackSyncState,
    FeedbackSyncStatus,
    FeedbackUnderstanding,
    ModuleFeedbackRecord,
    ModuleFeedbackRequest,
    ModuleFeedbackSummary,
)
from .versions import academy_version, adapter_version, nornyx_version


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def payload_digest(payload: dict[str, Any]) -> str:
    """Digest the payload's content, excluding the envelope that carries it.

    ``sync`` holds the digest itself and the generation timestamp, so including
    it would make every regeneration of an unchanged session look like a change
    and produce a pointless remote edit on each retry.
    """

    body = {key: value for key, value in payload.items() if key != "sync"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class FeedbackConfiguration:
    """Installation configuration. Non-secret by construction.

    There is no credential here and there is no field one could be placed in.
    ``endpoint`` is a URL an operator sets; when it is absent the feature is
    fully functional locally and simply cannot send.
    """

    endpoint: str | None = None
    destination_visibility: DestinationVisibility = DestinationVisibility.UNKNOWN
    timeout_seconds: float = 10.0

    @property
    def sending_configured(self) -> bool:
        return bool(self.endpoint)


class SQLiteFeedbackRepository:
    """Feedback storage, in the academy's existing SQLite file, in its own tables.

    Same database, entirely separate tables. Sharing the file keeps one thing to
    back up and one thing to mount; separate tables mean the migration is purely
    additive and no statement in this class can touch a row of learner evidence.

    Every table here is created with ``IF NOT EXISTS`` and nothing in this module
    issues ``ALTER``, ``UPDATE``, or ``DELETE`` against ``module_progress``,
    ``assessment_attempts``, or ``capstone_runs``.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        learner_id: str = "local",
        clock: Callable[[], str] = _utc_now,
        session_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.path = Path(path)
        self.learner_id = learner_id
        self._clock = clock
        # ``uuid4`` draws from the OS CSPRNG. The identifier is derived from
        # nothing about the learner, the machine, the browser, or the network —
        # it groups one validation session and is not an authenticated identity.
        self._session_factory = session_factory
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS feedback_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    schema_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    consent_state TEXT NOT NULL DEFAULT 'not_asked',
                    consent_at TEXT,
                    consent_document_version TEXT,
                    consent_destination TEXT,
                    revoked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback_consent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    consent_document_version TEXT NOT NULL,
                    destination_disclosure TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS module_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    learner_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    clarity INTEGER NOT NULL,
                    confidence INTEGER NOT NULL,
                    difficulty TEXT NOT NULL,
                    self_assessment TEXT NOT NULL,
                    comment TEXT,
                    module_status TEXT NOT NULL,
                    assessment_score REAL,
                    assessment_passed INTEGER,
                    assessment_attempts INTEGER NOT NULL DEFAULT 0,
                    competence_revision TEXT,
                    assessment_evidence_revision TEXT,
                    learning_path_id TEXT,
                    session_elapsed_seconds INTEGER,
                    academy_version TEXT NOT NULL,
                    nornyx_version TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    content_version TEXT NOT NULL,
                    UNIQUE (session_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS course_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    learner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    overall_clarity INTEGER NOT NULL,
                    progression INTEGER NOT NULL,
                    usefulness INTEGER NOT NULL,
                    final_confidence INTEGER NOT NULL,
                    overall_difficulty TEXT NOT NULL,
                    recommend TEXT NOT NULL,
                    most_helpful_module TEXT,
                    most_confusing_module TEXT,
                    missing_topic TEXT,
                    comments TEXT,
                    total_assessment_attempts INTEGER NOT NULL DEFAULT 0,
                    competence_revision TEXT,
                    learning_path_id TEXT,
                    session_elapsed_seconds INTEGER,
                    academy_version TEXT NOT NULL,
                    nornyx_version TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    content_version TEXT NOT NULL,
                    UNIQUE (session_id)
                );

                CREATE TABLE IF NOT EXISTS feedback_sync_state (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'never_attempted',
                    payload_digest TEXT,
                    synced_digest TEXT,
                    remote_reference TEXT,
                    remote_issue_number INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    last_error_code TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_module_feedback_session
                    ON module_feedback (session_id, module_id);
                """
            )
            self._reshape_pre_release_tables(connection)

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]

    def _reshape_pre_release_tables(self, connection: sqlite3.Connection) -> None:
        """Bring a database written by an earlier build of this unshipped feature up to date.

        ``CREATE TABLE IF NOT EXISTS`` is a no-op against a table that already
        exists, so a development database created before these columns settled
        keeps the old shape and every insert fails. The feedback tables have
        never appeared in a released version, so there is no production data at
        stake — but a developer's database is worth not destroying, so the
        course table is rebuilt by copying the columns that survived rather than
        dropped.

        Nothing here touches a learner-evidence table.
        """

        module_columns = self._columns(connection, "module_feedback")
        if "assessment_evidence_revision" not in module_columns:
            connection.execute(
                "ALTER TABLE module_feedback ADD COLUMN assessment_evidence_revision TEXT"
            )

        course_columns = self._columns(connection, "course_feedback")
        if "total_assessment_attempts" in course_columns:
            return
        # The old shape carried module-shaped placeholders that were never true
        # of a course-level rating. They are dropped rather than migrated: a
        # fabricated value has no correct destination.
        connection.executescript(
            """
            ALTER TABLE course_feedback RENAME TO course_feedback_pre_release;

            CREATE TABLE course_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                learner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                overall_clarity INTEGER NOT NULL,
                progression INTEGER NOT NULL,
                usefulness INTEGER NOT NULL,
                final_confidence INTEGER NOT NULL,
                overall_difficulty TEXT NOT NULL,
                recommend TEXT NOT NULL,
                most_helpful_module TEXT,
                most_confusing_module TEXT,
                missing_topic TEXT,
                comments TEXT,
                total_assessment_attempts INTEGER NOT NULL DEFAULT 0,
                competence_revision TEXT,
                learning_path_id TEXT,
                session_elapsed_seconds INTEGER,
                academy_version TEXT NOT NULL,
                nornyx_version TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                content_version TEXT NOT NULL,
                UNIQUE (session_id)
            );

            INSERT INTO course_feedback (
                id, session_id, learner_id, created_at, overall_clarity, progression,
                usefulness, final_confidence, overall_difficulty, recommend,
                most_helpful_module, most_confusing_module, missing_topic, comments,
                total_assessment_attempts, competence_revision, learning_path_id,
                session_elapsed_seconds, academy_version, nornyx_version,
                adapter_version, content_version
            )
            SELECT
                id, session_id, learner_id, created_at, overall_clarity, progression,
                usefulness, final_confidence, overall_difficulty, recommend,
                most_helpful_module, most_confusing_module, missing_topic, comments,
                assessment_attempts, competence_revision, learning_path_id,
                session_elapsed_seconds, academy_version, nornyx_version,
                adapter_version, content_version
            FROM course_feedback_pre_release;

            DROP TABLE course_feedback_pre_release;
            """
        )

    # ------------------------------------------------------------------ session
    def active_session(self) -> sqlite3.Row | None:
        with self._lock, self._connect() as connection:
            return connection.execute(
                """
                SELECT * FROM feedback_sessions
                WHERE learner_id = ? AND active = 1
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (self.learner_id,),
            ).fetchone()

    def ensure_session(self) -> sqlite3.Row:
        """Return the learner's open feedback session, opening one if needed.

        One open session per learner. The browser never supplies a session id,
        which removes client-side forgery from the picture entirely rather than
        trying to validate against it.
        """

        existing = self.active_session()
        if existing is not None:
            return existing
        session_id = self._session_factory()
        now = self._clock()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback_sessions (
                    session_id, learner_id, schema_id, created_at, active, consent_state
                ) VALUES (?, ?, ?, ?, 1, 'not_asked')
                """,
                (session_id, self.learner_id, FEEDBACK_SCHEMA_ID, now),
            )
            connection.execute(
                "INSERT INTO feedback_sync_state (session_id, status) VALUES (?, 'never_attempted')",
                (session_id,),
            )
        session = self.active_session()
        assert session is not None
        return session

    def set_consent(self, *, granted: bool, destination: str) -> sqlite3.Row:
        session = self.ensure_session()
        now = self._clock()
        with self._lock, self._connect() as connection:
            if granted:
                connection.execute(
                    """
                    UPDATE feedback_sessions
                    SET consent_state = 'granted', consent_at = ?,
                        consent_document_version = ?, consent_destination = ?, revoked_at = NULL
                    WHERE session_id = ?
                    """,
                    (now, CONSENT_DOCUMENT_VERSION, destination, session["session_id"]),
                )
            else:
                connection.execute(
                    """
                    UPDATE feedback_sessions
                    SET consent_state = 'revoked', revoked_at = ?
                    WHERE session_id = ?
                    """,
                    (now, session["session_id"]),
                )
            # Append-only. A revocation never erases the record that consent was
            # once given, because that is what authorised anything already sent.
            connection.execute(
                """
                INSERT INTO feedback_consent_events (
                    session_id, event, created_at, consent_document_version,
                    destination_disclosure
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session["session_id"],
                    "granted" if granted else "revoked",
                    now,
                    CONSENT_DOCUMENT_VERSION,
                    destination,
                ),
            )
        refreshed = self.active_session()
        assert refreshed is not None
        return refreshed

    def consent_events(self) -> tuple[dict[str, Any], ...]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM feedback_consent_events ORDER BY id"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    # ------------------------------------------------------------------ records
    def record_module_feedback(
        self,
        *,
        session_id: str,
        module_id: str,
        request: ModuleFeedbackRequest,
        context: FeedbackAcademyContext,
        content_version: str,
    ) -> int:
        now = self._clock()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO module_feedback (
                    session_id, learner_id, module_id, created_at, clarity, confidence,
                    difficulty, self_assessment, comment, module_status, assessment_score,
                    assessment_passed, assessment_attempts, competence_revision,
                    assessment_evidence_revision, learning_path_id, session_elapsed_seconds,
                    academy_version, nornyx_version, adapter_version, content_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id, module_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    clarity = excluded.clarity,
                    confidence = excluded.confidence,
                    difficulty = excluded.difficulty,
                    self_assessment = excluded.self_assessment,
                    comment = excluded.comment,
                    module_status = excluded.module_status,
                    assessment_score = excluded.assessment_score,
                    assessment_passed = excluded.assessment_passed,
                    assessment_attempts = excluded.assessment_attempts,
                    competence_revision = excluded.competence_revision,
                    assessment_evidence_revision = excluded.assessment_evidence_revision,
                    learning_path_id = excluded.learning_path_id,
                    session_elapsed_seconds = excluded.session_elapsed_seconds,
                    academy_version = excluded.academy_version,
                    nornyx_version = excluded.nornyx_version,
                    adapter_version = excluded.adapter_version,
                    content_version = excluded.content_version
                """,
                (
                    session_id,
                    self.learner_id,
                    module_id,
                    now,
                    request.clarity,
                    request.confidence,
                    request.difficulty.value,
                    request.self_assessment.value,
                    request.comment,
                    context.module_status.value,
                    context.assessment_score,
                    None if context.assessment_passed is None else int(context.assessment_passed),
                    context.assessment_attempts,
                    context.competence_revision,
                    context.assessment_evidence_revision,
                    context.learning_path_id,
                    context.session_elapsed_seconds,
                    academy_version(),
                    nornyx_version(),
                    adapter_version(),
                    content_version,
                ),
            )
            row = connection.execute(
                "SELECT id FROM module_feedback WHERE session_id = ? AND module_id = ?",
                (session_id, module_id),
            ).fetchone()
        assert row is not None
        return int(row["id"])

    def record_course_feedback(
        self,
        *,
        session_id: str,
        request: CourseFeedbackRequest,
        context: FeedbackCourseContext,
        content_version: str,
    ) -> int:
        now = self._clock()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO course_feedback (
                    session_id, learner_id, created_at, overall_clarity, progression,
                    usefulness, final_confidence, overall_difficulty, recommend,
                    most_helpful_module, most_confusing_module, missing_topic, comments,
                    total_assessment_attempts, competence_revision, learning_path_id,
                    session_elapsed_seconds, academy_version, nornyx_version,
                    adapter_version, content_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    overall_clarity = excluded.overall_clarity,
                    progression = excluded.progression,
                    usefulness = excluded.usefulness,
                    final_confidence = excluded.final_confidence,
                    overall_difficulty = excluded.overall_difficulty,
                    recommend = excluded.recommend,
                    most_helpful_module = excluded.most_helpful_module,
                    most_confusing_module = excluded.most_confusing_module,
                    missing_topic = excluded.missing_topic,
                    comments = excluded.comments,
                    total_assessment_attempts = excluded.total_assessment_attempts,
                    competence_revision = excluded.competence_revision,
                    learning_path_id = excluded.learning_path_id,
                    session_elapsed_seconds = excluded.session_elapsed_seconds,
                    academy_version = excluded.academy_version,
                    nornyx_version = excluded.nornyx_version,
                    adapter_version = excluded.adapter_version,
                    content_version = excluded.content_version
                """,
                (
                    session_id,
                    self.learner_id,
                    now,
                    request.overall_clarity,
                    request.progression,
                    request.usefulness,
                    request.final_confidence,
                    request.overall_difficulty.value,
                    request.recommend.value,
                    request.most_helpful_module,
                    request.most_confusing_module,
                    request.missing_topic,
                    request.comments,
                    context.total_assessment_attempts,
                    context.competence_revision,
                    context.learning_path_id,
                    context.session_elapsed_seconds,
                    academy_version(),
                    nornyx_version(),
                    adapter_version(),
                    content_version,
                ),
            )
            row = connection.execute(
                "SELECT id FROM course_feedback WHERE session_id = ?", (session_id,)
            ).fetchone()
        assert row is not None
        return int(row["id"])

    def module_rows(self, session_id: str) -> tuple[sqlite3.Row, ...]:
        with self._lock, self._connect() as connection:
            return tuple(
                connection.execute(
                    "SELECT * FROM module_feedback WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
            )

    def course_row(self, session_id: str) -> sqlite3.Row | None:
        with self._lock, self._connect() as connection:
            return connection.execute(
                "SELECT * FROM course_feedback WHERE session_id = ?", (session_id,)
            ).fetchone()

    def all_module_rows(self) -> tuple[sqlite3.Row, ...]:
        with self._lock, self._connect() as connection:
            return tuple(
                connection.execute(
                    "SELECT * FROM module_feedback WHERE learner_id = ? ORDER BY id",
                    (self.learner_id,),
                ).fetchall()
            )

    def all_course_rows(self) -> tuple[sqlite3.Row, ...]:
        with self._lock, self._connect() as connection:
            return tuple(
                connection.execute(
                    "SELECT * FROM course_feedback WHERE learner_id = ? ORDER BY id",
                    (self.learner_id,),
                ).fetchall()
            )

    # --------------------------------------------------------------- sync state
    def sync_row(self, session_id: str) -> sqlite3.Row:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO feedback_sync_state (session_id) VALUES (?) "
                "ON CONFLICT (session_id) DO NOTHING",
                (session_id,),
            )
            row = connection.execute(
                "SELECT * FROM feedback_sync_state WHERE session_id = ?", (session_id,)
            ).fetchone()
        assert row is not None
        return row

    def update_sync(
        self,
        session_id: str,
        *,
        status: FeedbackSyncStatus,
        digest: str | None = None,
        synced_digest: str | None = None,
        remote_reference: str | None = None,
        remote_issue_number: int | None = None,
        error_code: str | None = None,
        attempted: bool = False,
        succeeded: bool = False,
    ) -> None:
        now = self._clock()
        with self._lock, self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM feedback_sync_state WHERE session_id = ?", (session_id,)
            ).fetchone()
            attempts = (current["attempts"] if current else 0) + (1 if attempted else 0)
            connection.execute(
                """
                INSERT INTO feedback_sync_state (
                    session_id, status, payload_digest, synced_digest, remote_reference,
                    remote_issue_number, attempts, last_attempt_at, last_success_at,
                    last_error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    status = excluded.status,
                    payload_digest = COALESCE(excluded.payload_digest, payload_digest),
                    synced_digest = COALESCE(excluded.synced_digest, synced_digest),
                    remote_reference = COALESCE(excluded.remote_reference, remote_reference),
                    remote_issue_number = COALESCE(
                        excluded.remote_issue_number, remote_issue_number
                    ),
                    attempts = excluded.attempts,
                    last_attempt_at = COALESCE(excluded.last_attempt_at, last_attempt_at),
                    last_success_at = COALESCE(excluded.last_success_at, last_success_at),
                    last_error_code = excluded.last_error_code
                """,
                (
                    session_id,
                    status.value,
                    digest,
                    synced_digest,
                    remote_reference,
                    remote_issue_number,
                    attempts,
                    now if attempted else None,
                    now if succeeded else None,
                    error_code,
                ),
            )

    # ------------------------------------------------------------------ deletion
    def delete_all(self) -> tuple[int, int, bool]:
        """Remove every local feedback record. Returns (modules, course, was_sent).

        Deliberately separate from learner-progress reset, in both directions:
        deleting feedback leaves progress untouched, and resetting progress
        leaves feedback untouched.
        """

        with self._lock, self._connect() as connection:
            modules = connection.execute(
                "SELECT COUNT(*) AS n FROM module_feedback WHERE learner_id = ?",
                (self.learner_id,),
            ).fetchone()["n"]
            course = connection.execute(
                "SELECT COUNT(*) AS n FROM course_feedback WHERE learner_id = ?",
                (self.learner_id,),
            ).fetchone()["n"]
            submitted = connection.execute(
                """
                SELECT COUNT(*) AS n FROM feedback_sync_state
                WHERE synced_digest IS NOT NULL
                """
            ).fetchone()["n"]
            connection.execute(
                "DELETE FROM module_feedback WHERE learner_id = ?", (self.learner_id,)
            )
            connection.execute(
                "DELETE FROM course_feedback WHERE learner_id = ?", (self.learner_id,)
            )
            connection.execute(
                """
                DELETE FROM feedback_sync_state WHERE session_id IN (
                    SELECT session_id FROM feedback_sessions WHERE learner_id = ?
                )
                """,
                (self.learner_id,),
            )
            connection.execute(
                """
                DELETE FROM feedback_consent_events WHERE session_id IN (
                    SELECT session_id FROM feedback_sessions WHERE learner_id = ?
                )
                """,
                (self.learner_id,),
            )
            connection.execute(
                "DELETE FROM feedback_sessions WHERE learner_id = ?", (self.learner_id,)
            )
        return int(modules), int(course), bool(submitted)


# --------------------------------------------------------------------- service
#: What a learner is told *before* opting in. Deliberately not the word
#: "anonymous": free text can contain whatever someone types, and the network
#: and hosting layers between here and the maintainers are not this
#: application's to describe.
BASE_CONSENT_DISCLOSURE: tuple[str, ...] = (
    "What is sent: your 1-5 ratings, the difficulty and understanding choices you picked, "
    "anything you typed in the comment boxes, which module each rating was about, your "
    "assessment score and pass/fail for that module, and the version numbers this installation "
    "is running.",
    "What Nornyx Lab does not ask for or collect: your name, email address, GitHub account, "
    "computer name, username, file paths, IP address, browser or device identifiers, or your "
    "assessment answers.",
    "Free text is sent exactly as you type it. If you type something that identifies you or "
    "someone else, that is what will be sent — please leave personal or sensitive information "
    "out of the comment boxes.",
    "A random identifier groups this learning session's feedback together. It is not linked to "
    "you, your computer, or your network.",
)

#: Destination wording. An installation cannot inspect how the maintainers set
#: up their intake, so "unknown" is a real answer and is stated as one rather
#: than being dressed up as privacy.
DESTINATION_DISCLOSURE: dict[DestinationVisibility, str] = {
    DestinationVisibility.PUBLIC: (
        "Where it goes: this installation is configured to send feedback to a destination its "
        "operator has marked as public, which means what you write may become publicly visible."
    ),
    DestinationVisibility.PRIVATE: (
        "Where it goes: this installation is configured to send feedback to a destination its "
        "operator has marked as private, so it is not published publicly. That is the "
        "operator's setting; this installation cannot verify it independently."
    ),
    DestinationVisibility.UNKNOWN: (
        "Where it goes: this installation cannot confirm whether the destination is public or "
        "private, because that is decided where the feedback is received. Write your comments "
        "as if they could be read by anyone."
    ),
}


def consent_disclosure(visibility: DestinationVisibility) -> tuple[str, ...]:
    return (*BASE_CONSENT_DISCLOSURE, DESTINATION_DISCLOSURE[visibility])


#: What the learner is told, by state. The browser renders these strings; it does
#: not compose its own. A page cannot report "sent" while the record says failed.
LEARNER_MESSAGES: dict[str, str] = {
    "not_configured": (
        "Feedback is saved locally. This installation is not configured to send feedback to "
        "the maintainers."
    ),
    "no_consent": ("Feedback saved on this computer. Nothing has been sent to the maintainers."),
    "consented": (
        "Feedback saved on this computer. Future feedback from this learning session will "
        "also be sent to the maintainers."
    ),
    "unavailable": (
        "Your feedback is saved locally. Sending it to the maintainers is temporarily unavailable."
    ),
    "synced": ("Feedback saved on this computer and sent to the maintainers."),
    "empty": "No feedback has been recorded on this computer yet.",
}


class FeedbackService:
    """Composes storage, server-derived context, consent, and one bounded delivery attempt."""

    def __init__(
        self,
        repository: SQLiteFeedbackRepository,
        *,
        configuration: FeedbackConfiguration,
        assessment_outcome: Callable[[str], AdmissibleAssessment],
        content_version: str,
        transport: FeedbackTransport | None = None,
        competence: CompetenceContract | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.configuration = configuration
        self._assessment_outcome = assessment_outcome
        self._content_version = content_version
        self._transport = transport
        self._competence = competence or CompetenceContract.load()
        self._clock = clock

    # ------------------------------------------------------------------ context
    def _elapsed(self, session_started_at: str) -> int | None:
        """Seconds on the server clock between opening the session and now.

        Measured here rather than reported by the browser. A client-supplied
        duration would be one more thing a modified client could author, and
        this value is honestly measurable without asking it.
        """

        started = _parse(session_started_at)
        now = _parse(self._clock())
        if started is None or now is None:
            return None
        return max(0, int((now - started).total_seconds()))

    def _module_context(self, module_id: str, *, session_started_at: str) -> FeedbackAcademyContext:
        """Derive provenance from the learner record. Never from the request."""

        outcome = self._assessment_outcome(module_id)
        return FeedbackAcademyContext(
            module_status=outcome.status,
            assessment_score=outcome.best_score,
            assessment_passed=outcome.passed,
            assessment_attempts=outcome.attempts,
            competence_revision=self._competence.revision(EvidenceFamily.ASSESSMENT),
            assessment_evidence_revision=outcome.evidence_revision,
            # Every module belongs to more than one authored path and this
            # installation records no chosen path, so there is no authoritative
            # value. Unknown stays unknown rather than being inferred.
            learning_path_id=None,
            session_elapsed_seconds=self._elapsed(session_started_at),
        )

    def _course_context(
        self, *, session_started_at: str, total_attempts: int
    ) -> FeedbackCourseContext:
        """Course feedback is about the whole curriculum, so it binds to no module.

        It therefore carries no module status, module score, or module pass/fail
        — not even a placeholder. A structural ``not_started`` would sit in the
        research record looking exactly like an observed fact about a module,
        and there is no module for it to be a fact about.
        """

        return FeedbackCourseContext(
            total_assessment_attempts=total_attempts,
            competence_revision=self._competence.revision(EvidenceFamily.ASSESSMENT),
            learning_path_id=None,
            session_elapsed_seconds=self._elapsed(session_started_at),
        )

    # ---------------------------------------------------------------- submission
    def submit_module_feedback(
        self, module_id: str, request: ModuleFeedbackRequest
    ) -> FeedbackSubmissionResponse:
        session = self.repository.ensure_session()
        context = self._module_context(module_id, session_started_at=session["created_at"])
        # The local write happens first and is never conditional on the network.
        record_id = self.repository.record_module_feedback(
            session_id=session["session_id"],
            module_id=module_id,
            request=request,
            context=context,
            content_version=self._content_version,
        )
        self._sync_if_consented(session["session_id"])
        return FeedbackSubmissionResponse(saved=True, record_id=record_id, status=self.status())

    def submit_course_feedback(
        self, request: CourseFeedbackRequest, *, total_attempts: int
    ) -> FeedbackSubmissionResponse:
        session = self.repository.ensure_session()
        context = self._course_context(
            session_started_at=session["created_at"], total_attempts=total_attempts
        )
        record_id = self.repository.record_course_feedback(
            session_id=session["session_id"],
            request=request,
            context=context,
            content_version=self._content_version,
        )
        self._sync_if_consented(session["session_id"])
        return FeedbackSubmissionResponse(saved=True, record_id=record_id, status=self.status())

    def set_consent(self, *, granted: bool) -> FeedbackStatus:
        self.repository.set_consent(
            granted=granted,
            destination=self.configuration.destination_visibility.value,
        )
        if granted:
            session = self.repository.ensure_session()
            self._sync_if_consented(session["session_id"])
        return self.status()

    def delete_local_feedback(self) -> FeedbackDeletionResponse:
        modules, course, submitted = self.repository.delete_all()
        limitation = ""
        if submitted:
            limitation = (
                "Some of this feedback had already been sent to the maintainers. Deleting the "
                "local copy does not remove what was already received, and this installation "
                "cannot delete it for you."
            )
        return FeedbackDeletionResponse(
            deleted_module_records=modules,
            deleted_course_records=course,
            previously_submitted_externally=submitted,
            limitation=limitation,
            status=self.status(),
        )

    # ---------------------------------------------------------------------- sync
    def _sync_if_consented(self, session_id: str) -> None:
        """Attempt delivery only when the *stored* consent state permits it."""

        session = self.repository.active_session()
        if session is None or session["consent_state"] != FeedbackConsentState.GRANTED.value:
            return
        self.sync_now()

    def sync_now(self) -> FeedbackStatus:
        """One bounded attempt. Never a retry loop inside a learner request.

        A learner pressing a button should get an answer, not sit behind a
        backoff schedule. Failures are recorded honestly and the next submission
        or an explicit retry tries again.
        """

        session = self.repository.ensure_session()
        session_id = session["session_id"]

        if not self.configuration.sending_configured:
            self.repository.update_sync(session_id, status=FeedbackSyncStatus.NOT_CONFIGURED)
            return self.status()
        if session["consent_state"] != FeedbackConsentState.GRANTED.value:
            self.repository.update_sync(session_id, status=FeedbackSyncStatus.NO_CONSENT)
            return self.status()

        if not self.repository.module_rows(session_id) and (
            self.repository.course_row(session_id) is None
        ):
            # Consent with nothing to send is not a delivery. Transmitting an
            # empty session would open an issue containing no feedback, which
            # is noise for the maintainers and a network call the learner did
            # not ask for.
            return self.status()

        payload = self.build_payload(session_id)
        digest = payload["sync"]["payload_digest"]
        current = self.repository.sync_row(session_id)
        if (
            current["synced_digest"] == digest
            and current["status"] == FeedbackSyncStatus.SYNCED.value
        ):
            # Nothing changed since the last confirmed delivery. Sending again
            # would be a duplicate request for an identical record.
            return self.status()

        transport = self._transport
        if transport is None:
            from .feedback_client import UrllibFeedbackTransport

            transport = UrllibFeedbackTransport(timeout_seconds=self.configuration.timeout_seconds)
        assert self.configuration.endpoint is not None
        try:
            result: TransportResult = transport.send(self.configuration.endpoint, payload)
        except Exception:
            # Deliberately broad. The transport classifies every failure it
            # anticipates; this catches the ones it does not. The rating is
            # already committed, so whatever went wrong is an operational fact
            # about delivery — not a reason to return an error for an action
            # that succeeded. A narrower clause here would let an unforeseen
            # exception turn a saved rating into a failed request.
            result = TransportResult(ok=False, error_code="transport_error")
        if result.ok:
            self.repository.update_sync(
                session_id,
                status=FeedbackSyncStatus.SYNCED,
                digest=digest,
                synced_digest=digest,
                remote_reference=(
                    None if result.issue_number is None else f"issue #{result.issue_number}"
                ),
                remote_issue_number=result.issue_number,
                error_code=None,
                attempted=True,
                succeeded=True,
            )
        else:
            self.repository.update_sync(
                session_id,
                status=FeedbackSyncStatus.FAILED,
                digest=digest,
                error_code=result.error_code,
                attempted=True,
            )
        return self.status()

    # ------------------------------------------------------------------- payload
    def build_payload(self, session_id: str) -> dict[str, Any]:
        """The exact object that would be transmitted, and nothing more.

        Note what is not here: the learner id, any device or browser
        information, any filesystem path, any environment value, and the
        learner's assessment answers.
        """

        session = self.repository.ensure_session()
        modules = self.repository.module_rows(session_id)
        course = self.repository.course_row(session_id)
        payload: dict[str, Any] = {
            "schema_id": FEEDBACK_SCHEMA_ID,
            "session": {
                "session_id": session_id,
                "created_at": session["created_at"],
                "module_record_count": len(modules),
                "course_record_count": 1 if course is not None else 0,
            },
            "runtime": {
                "academy_version": academy_version(),
                "nornyx_version": nornyx_version(),
                "adapter_version": adapter_version(),
                "api_version": API_VERSION,
                "content_version": self._content_version,
            },
            "module_feedback": [
                {
                    "record_id": int(row["id"]),
                    "module_id": row["module_id"],
                    "created_at": row["created_at"],
                    "perception": {
                        "clarity": int(row["clarity"]),
                        "confidence": int(row["confidence"]),
                        "difficulty": row["difficulty"],
                        "self_assessment": row["self_assessment"],
                        "comment": row["comment"],
                    },
                    "academy_context": _context_payload(row),
                }
                for row in modules
            ],
            "course_feedback": (
                None
                if course is None
                else {
                    "record_id": int(course["id"]),
                    "created_at": course["created_at"],
                    "perception": {
                        "overall_clarity": int(course["overall_clarity"]),
                        "progression": int(course["progression"]),
                        "usefulness": int(course["usefulness"]),
                        "final_confidence": int(course["final_confidence"]),
                        "overall_difficulty": course["overall_difficulty"],
                        "recommend": course["recommend"],
                        "most_helpful_module": course["most_helpful_module"],
                        "most_confusing_module": course["most_confusing_module"],
                        "missing_topic": course["missing_topic"],
                        "comments": course["comments"],
                    },
                    "academy_context": _course_context_payload(course),
                }
            ),
        }
        payload["sync"] = {
            "payload_digest": payload_digest(payload),
            "generated_at": self._clock(),
        }
        return payload

    # -------------------------------------------------------------------- status
    def status(self) -> FeedbackStatus:
        session = self.repository.ensure_session()
        session_id = session["session_id"]
        sync = self.repository.sync_row(session_id)
        modules = self.repository.module_rows(session_id)
        course = self.repository.course_row(session_id)
        consent = FeedbackConsentState(session["consent_state"])

        status = FeedbackSyncStatus(sync["status"])
        if not self.configuration.sending_configured:
            status = FeedbackSyncStatus.NOT_CONFIGURED
        elif consent is not FeedbackConsentState.GRANTED and status in {
            FeedbackSyncStatus.NEVER_ATTEMPTED,
            FeedbackSyncStatus.NOT_CONFIGURED,
        }:
            status = FeedbackSyncStatus.NO_CONSENT

        has_records = bool(modules) or course is not None
        pending = False
        if has_records:
            pending = self.build_payload(session_id)["sync"]["payload_digest"] != (
                sync["synced_digest"] or ""
            )

        if not has_records:
            message = LEARNER_MESSAGES["empty"]
        elif not self.configuration.sending_configured:
            message = LEARNER_MESSAGES["not_configured"]
        elif consent is not FeedbackConsentState.GRANTED:
            message = LEARNER_MESSAGES["no_consent"]
        elif status is FeedbackSyncStatus.FAILED:
            message = LEARNER_MESSAGES["unavailable"]
        elif status is FeedbackSyncStatus.SYNCED and not pending:
            message = LEARNER_MESSAGES["synced"]
        else:
            message = LEARNER_MESSAGES["consented"]

        return FeedbackStatus(
            session_id=session_id,
            session_started_at=session["created_at"],
            consent_state=consent,
            consent_at=session["consent_at"],
            sending_configured=self.configuration.sending_configured,
            destination_visibility=self.configuration.destination_visibility,
            sync=FeedbackSyncState(
                status=status,
                attempts=int(sync["attempts"]),
                last_attempt_at=sync["last_attempt_at"],
                last_success_at=sync["last_success_at"],
                last_error_code=sync["last_error_code"],
                remote_reference=sync["remote_reference"],
                pending_changes=pending,
            ),
            module_feedback=tuple(_module_record(row) for row in modules),
            course_feedback=None if course is None else _course_record(course),
            learner_message=message,
            consent_disclosure=consent_disclosure(self.configuration.destination_visibility),
        )

    # ------------------------------------------------------------------- summary
    def summary(self) -> FeedbackSummary:
        """Counts, with the sample size always attached. No causal claims."""

        modules = self.repository.all_module_rows()
        grouped: dict[str, list[Any]] = {}
        for row in modules:
            grouped.setdefault(row["module_id"], []).append(row)

        summaries: list[ModuleFeedbackSummary] = []
        for module_id in sorted(grouped):
            rows = grouped[module_id]
            scored = [row for row in rows if row["assessment_passed"] is not None]
            summaries.append(
                ModuleFeedbackSummary(
                    module_id=module_id,
                    sample_count=len(rows),
                    average_clarity=_mean(row["clarity"] for row in rows),
                    average_confidence=_mean(row["confidence"] for row in rows),
                    difficulty_distribution=_distribution(row["difficulty"] for row in rows),
                    understanding_distribution=_distribution(
                        row["self_assessment"] for row in rows
                    ),
                    assessment_pass_rate=(
                        None
                        if not scored
                        else round(
                            sum(1 for row in scored if row["assessment_passed"]) / len(scored), 4
                        )
                    ),
                    confidence_pass_mismatch=sum(
                        1
                        for row in scored
                        if row["confidence"] >= 4 and not row["assessment_passed"]
                    ),
                )
            )

        course_rows = self.repository.all_course_rows()
        return FeedbackSummary(
            modules=tuple(summaries),
            course=CourseFeedbackSummary(
                sample_count=len(course_rows),
                average_overall_clarity=_mean(row["overall_clarity"] for row in course_rows),
                average_progression=_mean(row["progression"] for row in course_rows),
                average_usefulness=_mean(row["usefulness"] for row in course_rows),
                recommendation_distribution=_distribution(row["recommend"] for row in course_rows),
            ),
        )


def _mean(values: Iterable[float]) -> float | None:
    collected = list(values)
    if not collected:
        return None
    return round(sum(collected) / len(collected), 3)


def _distribution(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _context_payload(row: Any) -> dict[str, Any]:
    """The module-level provenance of one stored row, as transmitted."""

    passed = row["assessment_passed"]
    return {
        "module_status": row["module_status"],
        "assessment_score": row["assessment_score"],
        "assessment_passed": None if passed is None else bool(passed),
        "assessment_attempts": int(row["assessment_attempts"]),
        "competence_revision": row["competence_revision"],
        "assessment_evidence_revision": row["assessment_evidence_revision"],
        "learning_path_id": row["learning_path_id"],
        "session_elapsed_seconds": row["session_elapsed_seconds"],
    }


def _course_context_payload(row: Any) -> dict[str, Any]:
    """Course-level provenance. No module fields, not even empty ones."""

    return {
        "total_assessment_attempts": int(row["total_assessment_attempts"]),
        "competence_revision": row["competence_revision"],
        "learning_path_id": row["learning_path_id"],
        "session_elapsed_seconds": row["session_elapsed_seconds"],
    }


def _academy_context(row: Any) -> FeedbackAcademyContext:
    return FeedbackAcademyContext.model_validate(_context_payload(row))


def _course_context(row: Any) -> FeedbackCourseContext:
    return FeedbackCourseContext.model_validate(_course_context_payload(row))


def _module_record(row: Any) -> ModuleFeedbackRecord:
    return ModuleFeedbackRecord(
        record_id=int(row["id"]),
        module_id=row["module_id"],
        created_at=row["created_at"],
        clarity=int(row["clarity"]),
        confidence=int(row["confidence"]),
        difficulty=FeedbackDifficulty(row["difficulty"]),
        self_assessment=FeedbackUnderstanding(row["self_assessment"]),
        comment=row["comment"],
        academy_context=_academy_context(row),
    )


def _course_record(row: Any) -> CourseFeedbackRecord:
    return CourseFeedbackRecord(
        record_id=int(row["id"]),
        created_at=row["created_at"],
        overall_clarity=int(row["overall_clarity"]),
        progression=int(row["progression"]),
        usefulness=int(row["usefulness"]),
        final_confidence=int(row["final_confidence"]),
        overall_difficulty=FeedbackDifficulty(row["overall_difficulty"]),
        recommend=FeedbackRecommendation(row["recommend"]),
        most_helpful_module=row["most_helpful_module"],
        most_confusing_module=row["most_confusing_module"],
        missing_topic=row["missing_topic"],
        comments=row["comments"],
        academy_context=_course_context(row),
    )


__all__ = [
    "BASE_CONSENT_DISCLOSURE",
    "DESTINATION_DISCLOSURE",
    "LEARNER_MESSAGES",
    "FeedbackConfiguration",
    "FeedbackService",
    "SQLiteFeedbackRepository",
    "consent_disclosure",
    "payload_digest",
]

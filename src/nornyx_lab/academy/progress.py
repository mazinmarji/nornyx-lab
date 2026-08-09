"""Replaceable learner-record boundary with a local SQLite implementation."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .schemas import (
    AdvancedStanding,
    AssessmentResult,
    Dashboard,
    ModuleProgress,
    ModuleStatus,
    ProgressExport,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class LearnerRecordRepository(Protocol):
    """Persistence port kept independent from curriculum and HTTP concerns."""

    def record_execution(
        self,
        module_id: str,
        *,
        passed: bool,
        version_binding: dict[str, str] | None = None,
    ) -> ModuleProgress: ...

    def record_assessment(
        self,
        result: AssessmentResult,
        *,
        answers: tuple[str, ...],
        version_binding: dict[str, str] | None = None,
    ) -> ModuleProgress: ...

    def dashboard(self, module_ids: Iterable[str], *, capstone_id: str = "24") -> Dashboard: ...

    def reset(self) -> None: ...


class SQLiteLearnerRecordRepository:
    """Single-user default designed so a multi-user store can replace it later.

    The learner id is explicit in the schema even though the local experience
    uses one fixed identity.  No secret or live-model credential is stored here.

    Concept mastery is derived, never trusted from a stored aggregate: the
    evidence is the set of recorded assessment attempts, each granting only the
    concepts its assessment declares it tests.  A pre-remediation store whose
    ``module_progress.concepts_mastered`` column claimed every module concept
    therefore degrades safely to "completed, but mastery not yet demonstrated"
    instead of keeping fabricated mastery.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        learner_id: str = "local",
        clock: Callable[[], str] = _utc_now,
        assessment_concepts: Mapping[str, tuple[str, ...]] | None = None,
        module_concepts: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.path = Path(path)
        self.learner_id = learner_id
        self._clock = clock
        self._lock = threading.RLock()
        # Resolver for attempts recorded before per-attempt concepts were
        # stored: an old passed attempt re-derives evidence from what its
        # assessment declares today. An assessment that no longer exists
        # grants nothing — honest degradation, never invention.
        self._assessment_concepts = dict(assessment_concepts or {})
        self._module_concepts = dict(module_concepts or {})
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
                CREATE TABLE IF NOT EXISTS module_progress (
                    learner_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    executions INTEGER NOT NULL DEFAULT 0,
                    execution_passed INTEGER NOT NULL DEFAULT 0,
                    assessment_attempts INTEGER NOT NULL DEFAULT 0,
                    assessment_passed INTEGER NOT NULL DEFAULT 0,
                    best_score REAL,
                    concepts_mastered TEXT NOT NULL DEFAULT '[]',
                    concepts_needing_review TEXT NOT NULL DEFAULT '[]',
                    version_binding TEXT NOT NULL DEFAULT '{}',
                    last_activity TEXT,
                    PRIMARY KEY (learner_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS assessment_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    answers TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    feedback TEXT NOT NULL,
                    version_binding TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_assessment_learner_module
                    ON assessment_attempts (learner_id, module_id, created_at);
                """
            )
            # Additive migration for stores created before per-attempt concept
            # evidence existed. NULL marks a legacy attempt whose tested
            # concepts are re-derived from the current assessment declarations.
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(assessment_attempts)")
            }
            if "concepts_tested" not in columns:
                connection.execute(
                    "ALTER TABLE assessment_attempts ADD COLUMN concepts_tested TEXT"
                )
            # Capstone runs are recorded with their scaffolding level, scenario,
            # and authorship so the advanced gate can distinguish a scaffolded
            # walkthrough from learner-authored transfer work. A store created
            # before this table existed simply has no advanced evidence yet.
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS capstone_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    scaffolding TEXT NOT NULL,
                    completion_eligible INTEGER NOT NULL,
                    learner_authored INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _ensure_row(self, connection: sqlite3.Connection, module_id: str) -> None:
        connection.execute(
            """
            INSERT INTO module_progress (learner_id, module_id)
            VALUES (?, ?)
            ON CONFLICT (learner_id, module_id) DO NOTHING
            """,
            (self.learner_id, module_id),
        )

    @staticmethod
    def _status(row: sqlite3.Row) -> ModuleStatus:
        if row["execution_passed"] and row["assessment_passed"]:
            return ModuleStatus.COMPLETE
        if row["assessment_attempts"] and not row["assessment_passed"]:
            return ModuleStatus.NEEDS_REVIEW
        if row["executions"] or row["assessment_attempts"]:
            return ModuleStatus.IN_PROGRESS
        return ModuleStatus.NOT_STARTED

    def _attempt_concepts(self, row: sqlite3.Row) -> tuple[str, ...]:
        stored = row["concepts_tested"]
        if stored is not None:
            return tuple(json.loads(stored))
        return tuple(self._assessment_concepts.get(row["assessment_id"], ()))

    def _concept_evidence(
        self, connection: sqlite3.Connection
    ) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
        """Derive mastery evidence from the recorded attempts.

        Returns the global evidence set (a concept demonstrated anywhere counts
        wherever it is taught), per-module evidence, and per-module concepts
        tested by failed attempts.
        """

        rows = connection.execute(
            """
            SELECT assessment_id, module_id, passed, concepts_tested
            FROM assessment_attempts WHERE learner_id = ?
            """,
            (self.learner_id,),
        ).fetchall()
        evidence: set[str] = set()
        module_evidence: dict[str, set[str]] = {}
        module_failed: dict[str, set[str]] = {}
        for row in rows:
            concepts = set(self._attempt_concepts(row))
            if row["passed"]:
                evidence |= concepts
                module_evidence.setdefault(row["module_id"], set()).update(concepts)
            else:
                module_failed.setdefault(row["module_id"], set()).update(concepts)
        return evidence, module_evidence, module_failed

    def _as_progress(
        self,
        row: sqlite3.Row,
        *,
        evidence: set[str],
        module_evidence: dict[str, set[str]],
        module_failed: dict[str, set[str]],
    ) -> ModuleProgress:
        # The stored concepts_mastered aggregate is deliberately ignored: a
        # legacy store granted every module concept for one pass, and reading
        # it back would preserve exactly that fabricated mastery.
        module_id = row["module_id"]
        taught = self._module_concepts.get(module_id)
        if taught is not None:
            mastered = sorted(set(taught) & evidence)
            pending = sorted(set(taught) - evidence)
        else:
            mastered = sorted(module_evidence.get(module_id, set()))
            pending = []
        review = sorted(module_failed.get(module_id, set()) - evidence)
        return ModuleProgress(
            module_id=module_id,
            status=self._status(row),
            executions=row["executions"],
            assessment_attempts=row["assessment_attempts"],
            best_score=row["best_score"],
            last_activity=row["last_activity"],
            concepts_mastered=tuple(mastered),
            concepts_needing_review=tuple(review),
            concepts_pending_evidence=tuple(pending),
        )

    def get(self, module_id: str) -> ModuleProgress:
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, module_id)
            row = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ? AND module_id = ?",
                (self.learner_id, module_id),
            ).fetchone()
            assert row is not None
            evidence, module_evidence, module_failed = self._concept_evidence(connection)
            return self._as_progress(
                row,
                evidence=evidence,
                module_evidence=module_evidence,
                module_failed=module_failed,
            )

    def record_execution(
        self,
        module_id: str,
        *,
        passed: bool,
        version_binding: dict[str, str] | None = None,
    ) -> ModuleProgress:
        now = self._clock()
        binding = json.dumps(version_binding or {}, sort_keys=True)
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, module_id)
            connection.execute(
                """
                UPDATE module_progress
                SET executions = executions + 1,
                    execution_passed = MAX(execution_passed, ?),
                    version_binding = ?,
                    last_activity = ?
                WHERE learner_id = ? AND module_id = ?
                """,
                (int(passed), binding, now, self.learner_id, module_id),
            )
            row = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ? AND module_id = ?",
                (self.learner_id, module_id),
            ).fetchone()
            assert row is not None
            evidence, module_evidence, module_failed = self._concept_evidence(connection)
            return self._as_progress(
                row,
                evidence=evidence,
                module_evidence=module_evidence,
                module_failed=module_failed,
            )

    def record_assessment(
        self,
        result: AssessmentResult,
        *,
        answers: tuple[str, ...],
        version_binding: dict[str, str] | None = None,
    ) -> ModuleProgress:
        now = self._clock()
        binding = json.dumps(version_binding or {}, sort_keys=True)
        # The concepts this attempt tested, stored per attempt. Mastery is
        # derived from these records; the module_progress aggregate columns are
        # legacy and no longer read.
        tested = json.dumps(
            sorted(set(result.concepts_mastered) | set(result.concepts_needing_review))
        )
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, result.module_id)
            connection.execute(
                """
                INSERT INTO assessment_attempts (
                    learner_id, assessment_id, module_id, answers, score, passed,
                    feedback, version_binding, created_at, concepts_tested
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.learner_id,
                    result.assessment_id,
                    result.module_id,
                    json.dumps(answers),
                    result.score,
                    int(result.passed),
                    json.dumps(result.feedback),
                    binding,
                    now,
                    tested,
                ),
            )
            connection.execute(
                """
                UPDATE module_progress
                SET assessment_attempts = assessment_attempts + 1,
                    assessment_passed = MAX(assessment_passed, ?),
                    best_score = CASE
                        WHEN best_score IS NULL OR ? > best_score THEN ?
                        ELSE best_score
                    END,
                    version_binding = ?,
                    last_activity = ?
                WHERE learner_id = ? AND module_id = ?
                """,
                (
                    int(result.passed),
                    result.score,
                    result.score,
                    binding,
                    now,
                    self.learner_id,
                    result.module_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ? AND module_id = ?",
                (self.learner_id, result.module_id),
            ).fetchone()
            assert row is not None
            evidence, module_evidence, module_failed = self._concept_evidence(connection)
            return self._as_progress(
                row,
                evidence=evidence,
                module_evidence=module_evidence,
                module_failed=module_failed,
            )

    def record_capstone_run(
        self,
        *,
        run_id: str,
        scenario: str,
        scaffolding: str,
        completion_eligible: bool,
        learner_authored: bool,
    ) -> None:
        """Record one capstone execution as advanced-gate evidence.

        Only what actually happened is stored: the scaffolding level the run
        used, whether the design was learner-authored, and whether the run was
        completion-eligible. The gate never upgrades a scaffolded run.
        """

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO capstone_runs (
                    learner_id, run_id, scenario, scaffolding,
                    completion_eligible, learner_authored, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.learner_id,
                    run_id,
                    scenario,
                    scaffolding,
                    int(completion_eligible),
                    int(learner_authored),
                    self._clock(),
                ),
            )

    def _advanced_standing(
        self,
        connection: sqlite3.Connection,
        *,
        capstone_id: str,
        capstone_status: ModuleStatus,
        evidence: set[str],
    ) -> AdvancedStanding:
        rows = connection.execute(
            """
            SELECT scenario, scaffolding, completion_eligible, learner_authored
            FROM capstone_runs WHERE learner_id = ?
            """,
            (self.learner_id,),
        ).fetchall()
        eligible = [row for row in rows if row["completion_eligible"]]
        independent = any(
            row["scaffolding"] == "independent" and row["learner_authored"] for row in eligible
        )
        transfer = any(
            row["scenario"] != "customer-remediation"
            and row["scaffolding"] != "guided"
            and row["learner_authored"]
            for row in eligible
        )
        content_complete = capstone_status is ModuleStatus.COMPLETE
        capstone_concepts = set(self._assessment_concepts.get(f"assessment.{capstone_id}", ()))
        concepts_demonstrated = bool(capstone_concepts) and capstone_concepts <= evidence
        advanced = content_complete and concepts_demonstrated and independent and transfer
        missing = [
            label
            for label, satisfied in (
                ("capstone content completion", content_complete),
                ("capstone concept evidence", concepts_demonstrated),
                ("an independent learner-authored capstone", independent),
                ("a completion-eligible transfer-scenario design", transfer),
            )
            if not satisfied
        ]
        note = (
            "Advanced competence demonstrated: instructional completion, capstone concept "
            "evidence, independent authorship, and transfer are all on record."
            if advanced
            else "Not yet advanced. Still required: " + "; ".join(missing) + "."
        )
        return AdvancedStanding(
            capstone_content_complete=content_complete,
            capstone_concepts_demonstrated=concepts_demonstrated,
            independent_authorship_demonstrated=independent,
            transfer_demonstrated=transfer,
            advanced_competence_demonstrated=advanced,
            note=note,
        )

    def dashboard(self, module_ids: Iterable[str], *, capstone_id: str = "24") -> Dashboard:
        ordered = tuple(dict.fromkeys(module_ids))
        with self._lock, self._connect() as connection:
            for module_id in ordered:
                self._ensure_row(connection, module_id)
            rows = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ?",
                (self.learner_id,),
            ).fetchall()
            evidence, module_evidence, module_failed = self._concept_evidence(connection)
            by_id = {
                row["module_id"]: self._as_progress(
                    row,
                    evidence=evidence,
                    module_evidence=module_evidence,
                    module_failed=module_failed,
                )
                for row in rows
            }
            capstone = by_id.get(capstone_id)
            standing = self._advanced_standing(
                connection,
                capstone_id=capstone_id,
                capstone_status=(capstone.status if capstone else ModuleStatus.NOT_STARTED),
                evidence=evidence,
            )
        modules = tuple(by_id[module_id] for module_id in ordered)
        completed = sum(item.status == ModuleStatus.COMPLETE for item in modules)
        active = [item for item in modules if item.status != ModuleStatus.NOT_STARTED]
        current = next(
            (
                item.module_id
                for item in modules
                if item.status in {ModuleStatus.IN_PROGRESS, ModuleStatus.NEEDS_REVIEW}
            ),
            next(
                (item.module_id for item in modules if item.status != ModuleStatus.COMPLETE), None
            ),
        )
        mastered = sorted({concept for item in modules for concept in item.concepts_mastered})
        review = sorted({concept for item in modules for concept in item.concepts_needing_review})
        pending = sorted(
            {concept for item in modules for concept in item.concepts_pending_evidence}
            - set(mastered)
        )
        last = max((item.last_activity for item in active if item.last_activity), default=None)
        return Dashboard(
            modules=modules,
            completed_modules=completed,
            total_modules=len(modules),
            completion_percent=round((completed / len(modules) * 100) if modules else 0, 1),
            current_module_id=current,
            last_activity=last,
            concepts_mastered=tuple(mastered),
            concepts_needing_review=tuple(review),
            concepts_pending_evidence=tuple(pending),
            capstone_status=(capstone.status if capstone else ModuleStatus.NOT_STARTED),
            advanced_standing=standing,
        )

    def assessment_history(self) -> tuple[dict[str, Any], ...]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT assessment_id, module_id, answers, score, passed, feedback,
                       version_binding, created_at
                FROM assessment_attempts
                WHERE learner_id = ?
                ORDER BY created_at, id
                """,
                (self.learner_id,),
            ).fetchall()
        return tuple(
            {
                "assessment_id": row["assessment_id"],
                "module_id": row["module_id"],
                "answers": json.loads(row["answers"]),
                "score": row["score"],
                "passed": bool(row["passed"]),
                "feedback": json.loads(row["feedback"]),
                "version_binding": json.loads(row["version_binding"]),
                "created_at": row["created_at"],
            }
            for row in rows
        )

    def export(self, module_ids: Iterable[str]) -> ProgressExport:
        return ProgressExport(
            generated_at=self._clock(),
            learner_id=self.learner_id,
            dashboard=self.dashboard(module_ids),
            assessment_history=self.assessment_history(),
            assurance_note=(
                "This local completion report records academy executions and assessments. "
                "It is not an identity credential, certification, independent attestation, "
                "or proof that a real external system was governed."
            ),
        )

    def reset(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM assessment_attempts WHERE learner_id = ?", (self.learner_id,)
            )
            connection.execute(
                "DELETE FROM module_progress WHERE learner_id = ?", (self.learner_id,)
            )
            connection.execute("DELETE FROM capstone_runs WHERE learner_id = ?", (self.learner_id,))

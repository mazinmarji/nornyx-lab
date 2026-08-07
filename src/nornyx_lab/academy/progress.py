"""Replaceable learner-record boundary with a local SQLite implementation."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .schemas import (
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
    """

    def __init__(
        self,
        path: str | Path,
        *,
        learner_id: str = "local",
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.path = Path(path)
        self.learner_id = learner_id
        self._clock = clock
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

    def _as_progress(self, row: sqlite3.Row) -> ModuleProgress:
        return ModuleProgress(
            module_id=row["module_id"],
            status=self._status(row),
            executions=row["executions"],
            assessment_attempts=row["assessment_attempts"],
            best_score=row["best_score"],
            last_activity=row["last_activity"],
            concepts_mastered=tuple(json.loads(row["concepts_mastered"])),
            concepts_needing_review=tuple(json.loads(row["concepts_needing_review"])),
        )

    def get(self, module_id: str) -> ModuleProgress:
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, module_id)
            row = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ? AND module_id = ?",
                (self.learner_id, module_id),
            ).fetchone()
            assert row is not None
            return self._as_progress(row)

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
            return self._as_progress(row)

    def record_assessment(
        self,
        result: AssessmentResult,
        *,
        answers: tuple[str, ...],
        version_binding: dict[str, str] | None = None,
    ) -> ModuleProgress:
        now = self._clock()
        binding = json.dumps(version_binding or {}, sort_keys=True)
        mastered = json.dumps(sorted(set(result.concepts_mastered)))
        review = json.dumps(sorted(set(result.concepts_needing_review)))
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, result.module_id)
            connection.execute(
                """
                INSERT INTO assessment_attempts (
                    learner_id, assessment_id, module_id, answers, score, passed,
                    feedback, version_binding, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    concepts_mastered = CASE WHEN ? THEN ? ELSE concepts_mastered END,
                    concepts_needing_review = CASE WHEN ? THEN '[]' ELSE ? END,
                    version_binding = ?,
                    last_activity = ?
                WHERE learner_id = ? AND module_id = ?
                """,
                (
                    int(result.passed),
                    result.score,
                    result.score,
                    int(result.passed),
                    mastered,
                    int(result.passed),
                    review,
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
            return self._as_progress(row)

    def dashboard(self, module_ids: Iterable[str], *, capstone_id: str = "24") -> Dashboard:
        ordered = tuple(dict.fromkeys(module_ids))
        with self._lock, self._connect() as connection:
            for module_id in ordered:
                self._ensure_row(connection, module_id)
            rows = connection.execute(
                "SELECT * FROM module_progress WHERE learner_id = ?",
                (self.learner_id,),
            ).fetchall()
        by_id = {row["module_id"]: self._as_progress(row) for row in rows}
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
        last = max((item.last_activity for item in active if item.last_activity), default=None)
        capstone = by_id.get(capstone_id)
        return Dashboard(
            modules=modules,
            completed_modules=completed,
            total_modules=len(modules),
            completion_percent=round((completed / len(modules) * 100) if modules else 0, 1),
            current_module_id=current,
            last_activity=last,
            concepts_mastered=tuple(mastered),
            concepts_needing_review=tuple(review),
            capstone_status=(capstone.status if capstone else ModuleStatus.NOT_STARTED),
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

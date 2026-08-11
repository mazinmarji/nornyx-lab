"""Gateway-side synchronisation state.

The gateway is a relay, not an archive. This store holds only what idempotency
needs — which issue represents which session, and the digest last written to it.
It deliberately does **not** store learner free text, ratings, or academy
context: once a payload has been rendered into an issue, keeping a second copy
here would create a second place for the same words to leak from, with no
operational benefit.

Losing this database is survivable rather than duplicating: an unknown session
falls back to recovery against GitHub itself.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionRecord:
    #: The derived public marker, never the session UUID. The gateway has no
    #: reason to persist a write key, so it does not.
    session_marker: str
    issue_number: int
    payload_digest: str
    created_at: str
    updated_at: str


class SyncStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            existing = {
                row[1] for row in connection.execute("PRAGMA table_info(feedback_sessions)")
            }
            if existing and "session_marker" not in existing:
                # A pre-release store keyed by the raw session UUID. Dropped
                # rather than migrated, deliberately: the point of the change is
                # that the gateway does not hold write keys, so carrying the old
                # ones forward would defeat it. Nothing is lost that matters —
                # this table is a cache, and an unknown session is recovered from
                # GitHub by its marker.
                connection.execute("DROP TABLE feedback_sessions")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_sessions (
                    session_marker TEXT PRIMARY KEY,
                    issue_number INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def lookup(self, marker: str) -> SessionRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_sessions WHERE session_marker = ?", (marker,)
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_marker=row["session_marker"],
            issue_number=row["issue_number"],
            payload_digest=row["payload_digest"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def remember(self, *, marker: str, issue_number: int, digest: str, now: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback_sessions (
                    session_marker, issue_number, payload_digest, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (session_marker) DO UPDATE SET
                    issue_number = excluded.issue_number,
                    payload_digest = excluded.payload_digest,
                    updated_at = excluded.updated_at
                """,
                (marker, issue_number, digest, now, now),
            )


__all__ = ["SessionRecord", "SyncStore"]

"""The one issue per session rule, and how it survives retries and restarts.

The decision is deliberately readable in one place:

    known session, same digest   -> unchanged   (no network write at all)
    known session, new digest    -> update      (same issue number)
    unknown session, marker found on GitHub -> update, and re-learn the number
    unknown session, nothing found          -> create

The third branch is the one that matters. A create can succeed on GitHub and
still fail to reach the gateway — a timeout after the write, a dropped
connection, a restart between the two. Without recovery, the next attempt would
create a second issue for the same session and the maintainers would be reading
two partial records as if they were two learners. Recovery makes the operation
idempotent against the only authority that actually knows: GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .github import GitHubSink
from .models import FeedbackPayload
from .render import issue_body, issue_title, session_marker
from .store import SyncStore

Outcome = Literal["created", "updated", "unchanged"]


@dataclass(frozen=True)
class SyncResult:
    status: Outcome
    issue_number: int


def synchronise(
    payload: FeedbackPayload,
    *,
    sink: GitHubSink,
    store: SyncStore,
    now: str,
) -> SyncResult:
    session_id = payload.session.session_id
    digest = payload.sync.payload_digest
    known = store.lookup(session_id)

    if known is not None and known.payload_digest == digest:
        # Identical payload for a session already written. Doing nothing is the
        # correct behaviour: an update here would be a no-op edit that adds a
        # timeline entry to the issue for every retry.
        return SyncResult("unchanged", known.issue_number)

    body = issue_body(payload)
    title = issue_title(session_id)

    if known is not None:
        sink.update_issue(number=known.issue_number, body=body)
        store.remember(
            session_id=session_id, issue_number=known.issue_number, digest=digest, now=now
        )
        return SyncResult("updated", known.issue_number)

    recovered = sink.find_issue(title=title, marker=session_marker(session_id))
    if recovered is not None:
        sink.update_issue(number=recovered, body=body)
        store.remember(session_id=session_id, issue_number=recovered, digest=digest, now=now)
        return SyncResult("updated", recovered)

    number = sink.create_issue(title=title, body=body)
    store.remember(session_id=session_id, issue_number=number, digest=digest, now=now)
    return SyncResult("created", number)


__all__ = ["Outcome", "SyncResult", "synchronise"]

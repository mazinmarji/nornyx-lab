"""Shared fixtures: a substituted GitHub boundary and a valid payload factory.

Every test here runs against ``FakeGitHub``. That is not a convenience — it is
the rule the deployment depends on: no CI job in this repository may require a
real GitHub credential, so the only implementation that talks to github.com is
covered by tests that drive a fake ``urlopen`` instead.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from nornyx_feedback_gateway.config import SCHEMA_ID, GatewayConfig
from nornyx_feedback_gateway.github import GitHubError
from nornyx_feedback_gateway.store import SyncStore

SESSION_ID = "7f21ac1e-4b3d-4c2a-9f10-2b5d6e7a8c90"


class FakeGitHub:
    """An in-memory stand-in for the issue surface the gateway actually uses."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, str]] = {}
        self.next_number = 1
        self.calls: list[tuple[str, Any]] = []
        #: Set to raise from the next call of the named operation.
        self.fail_on: dict[str, GitHubError] = {}
        #: When true, ``create_issue`` writes the issue and *then* fails, which
        #: is the ambiguous-timeout case the idempotency model exists for.
        self.create_then_fail: GitHubError | None = None

    def _maybe_fail(self, operation: str) -> None:
        error = self.fail_on.pop(operation, None)
        if error is not None:
            raise error

    def find_issue(self, *, title: str, marker: str) -> int | None:
        self.calls.append(("find", title))
        self._maybe_fail("find_issue")
        for number, issue in self.issues.items():
            if issue["title"] == title and marker in issue["body"]:
                return number
        return None

    def create_issue(self, *, title: str, body: str) -> int:
        self.calls.append(("create", title))
        self._maybe_fail("create_issue")
        number = self.next_number
        self.next_number += 1
        self.issues[number] = {"title": title, "body": body}
        if self.create_then_fail is not None:
            error = self.create_then_fail
            self.create_then_fail = None
            raise error
        return number

    def update_issue(self, *, number: int, body: str) -> None:
        self.calls.append(("update", number))
        self._maybe_fail("update_issue")
        if number not in self.issues:
            raise GitHubError("not_found", "no such issue", status=404)
        self.issues[number]["body"] = body


@pytest.fixture
def config(tmp_path) -> GatewayConfig:
    return GatewayConfig(
        github_repository="nornyx-maintainers/nornyx-lab-feedback-intake",
        github_token="ghp-test-token-value-never-echoed",
        database_path=str(tmp_path / "gateway.db"),
        destination_visibility="private",
    )


@pytest.fixture
def store(tmp_path) -> SyncStore:
    return SyncStore(tmp_path / "gateway.db")


@pytest.fixture
def sink() -> FakeGitHub:
    return FakeGitHub()


def digest_of(payload: dict[str, Any]) -> str:
    body = copy.deepcopy(payload)
    body.pop("sync", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def make_payload(
    *,
    session_id: str = SESSION_ID,
    comment: str | None = "The counters section finally made it click.",
    clarity: int = 4,
    with_course: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "session": {
            "session_id": session_id,
            "created_at": "2026-08-10T12:00:00Z",
            "module_record_count": 1,
            "course_record_count": 1 if with_course else 0,
        },
        "runtime": {
            "academy_version": "2.0.0",
            "nornyx_version": "1.11.0",
            "adapter_version": "0.3.0",
            "api_version": "v1",
            "content_version": "2026.08.1",
        },
        "module_feedback": [
            {
                "record_id": 1,
                "module_id": "F0",
                "created_at": "2026-08-10T12:05:00Z",
                "perception": {
                    "clarity": clarity,
                    "confidence": 3,
                    "difficulty": "right_level",
                    "self_assessment": "understood",
                    "comment": comment,
                },
                "academy_context": {
                    "module_status": "complete",
                    "assessment_score": 1.0,
                    "assessment_passed": True,
                    "assessment_attempts": 1,
                    "competence_revision": "assessment.2026-08-10",
                    "learning_path_id": None,
                    "session_elapsed_seconds": 320,
                },
            }
        ],
        "course_feedback": (
            {
                "record_id": 1,
                "created_at": "2026-08-10T12:30:00Z",
                "perception": {
                    "overall_clarity": 4,
                    "progression": 5,
                    "usefulness": 4,
                    "final_confidence": 3,
                    "overall_difficulty": "right_level",
                    "recommend": "yes",
                    "most_helpful_module": "F0",
                    "most_confusing_module": None,
                    "missing_topic": None,
                    "comments": None,
                },
                "academy_context": {
                    "module_status": "complete",
                    "assessment_score": None,
                    "assessment_passed": None,
                    "assessment_attempts": 3,
                    "competence_revision": "assessment.2026-08-10",
                    "learning_path_id": None,
                    "session_elapsed_seconds": 1800,
                },
            }
            if with_course
            else None
        ),
        "sync": {"payload_digest": "", "generated_at": "2026-08-10T12:31:00Z"},
    }
    payload["sync"]["payload_digest"] = digest_of(payload)
    return payload

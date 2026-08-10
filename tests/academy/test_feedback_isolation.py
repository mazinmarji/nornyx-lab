"""Feedback is instrumentation. It must never become evidence.

The academy's competence model is built on recorded executions, scored
assessments, and the semantic revision each was earned under. What a learner
*felt* about a lesson belongs to none of that. This module is the enforcement of
that separation, in three independent ways, because any one of them alone could
be satisfied by an implementation that still leaked:

1. **Behavioural.** Identical work with every rating at 1/5 and with every
   rating at 5/5 must produce byte-identical competence output.
2. **Structural.** No module that derives competence may import, mention, or
   read anything from the feedback feature.
3. **Distributional.** No GitHub credential symbol may exist anywhere in what a
   learner installation actually ships.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import FeedbackConfiguration
from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository
from nornyx_lab.academy.schemas import DestinationVisibility, ModuleStatus

SOURCE = Path(__file__).resolve().parents[2] / "src" / "nornyx_lab"
REPOSITORY = Path(__file__).resolve().parents[2]

#: The modules that decide what a learner has demonstrated. If any of these ever
#: learns what feedback is, the separation this feature depends on is gone.
COMPETENCE_MODULES = (
    "academy/progress.py",
    "academy/competence.py",
    "academy/advanced.py",
    "academy/capstone.py",
    "academy/assessments.py",
    "academy/catalog.py",
    "academy/foundations.py",
    "academy/structured.py",
    "academy/scenarios.py",
    "academy/pedagogy.py",
)


def _client(tmp_path: Path, **kwargs) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=None, destination_visibility=DestinationVisibility.UNKNOWN
            ),
            **kwargs,
        )
    )


def _earn_some_competence(client: TestClient) -> None:
    """Do real work: run modules and pass their assessments."""

    for module_id in ("F0", "F1", "F2"):
        run = client.post(f"/api/v1/modules/{module_id}/run")
        assert run.status_code == 200, run.text
        assessment_id = f"assessment.{module_id}"
        definition = client.app.state.assessments.definition(assessment_id)
        submitted = client.post(
            f"/api/v1/assessments/{assessment_id}/submit",
            json={"answers": list(definition.correct)},
        )
        assert submitted.status_code == 200, submitted.text


def _rate_everything(client: TestClient, value: int) -> None:
    difficulty = "too_hard" if value == 1 else "too_easy"
    understanding = "still_confused" if value == 1 else "understood"
    for module_id in ("F0", "F1", "F2"):
        response = client.post(
            f"/api/v1/feedback/modules/{module_id}",
            json={
                "clarity": value,
                "confidence": value,
                "difficulty": difficulty,
                "self_assessment": understanding,
                "comment": f"rated {value}",
            },
        )
        assert response.status_code == 200, response.text
    course = client.post(
        "/api/v1/feedback/course",
        json={
            "overall_clarity": value,
            "progression": value,
            "usefulness": value,
            "final_confidence": value,
            "overall_difficulty": difficulty,
            "recommend": "no" if value == 1 else "yes",
            "comments": f"course rated {value}",
        },
    )
    assert course.status_code == 200, course.text


def _competence_snapshot(client: TestClient, *, drop_wall_clock: bool = False) -> str:
    """Everything the academy says about what the learner has demonstrated.

    ``drop_wall_clock`` removes the timestamps two *separate* runs cannot share.
    It is deliberately off by default: within one installation, feedback must
    not move ``last_activity`` either, and keeping it in the comparison is what
    proves feedback never touches ``module_progress`` at all.
    """

    dashboard = client.get("/api/v1/progress").json()
    export = client.get("/api/v1/progress/export").json()
    catalog = client.get("/api/v1/catalog").json()
    export.pop("generated_at", None)
    for attempt in export.get("assessment_history", []):
        attempt.pop("created_at", None)
    if drop_wall_clock:
        dashboard.pop("last_activity", None)
        export["dashboard"].pop("last_activity", None)
        for item in dashboard["modules"]:
            item.pop("last_activity", None)
        for item in export["dashboard"]["modules"]:
            item.pop("last_activity", None)
    return json.dumps(
        {
            "dashboard": dashboard,
            "export": export,
            "module_status": [
                {"id": item["id"], "status": item["status"], "score": item["score"]}
                for item in catalog["modules"]
            ],
        },
        sort_keys=True,
    )


# -------------------------------------------------------------- behavioural
def test_all_one_and_all_five_feedback_produce_identical_competence_output(tmp_path) -> None:
    """The headline regression.

    Same executions, same assessment evidence, opposite opinions. If a single
    byte of competence output moves, feedback has become evidence.
    """

    with _client(tmp_path) as client:
        _earn_some_competence(client)
        baseline = _competence_snapshot(client)

        _rate_everything(client, 1)
        after_worst = _competence_snapshot(client)

        assert client.delete("/api/v1/feedback").status_code == 200
        _rate_everything(client, 5)
        after_best = _competence_snapshot(client)

    assert after_worst == baseline, "1/5 feedback changed the competence record"
    assert after_best == baseline, "5/5 feedback changed the competence record"
    assert after_worst == after_best


def test_two_installations_differing_only_in_ratings_agree_on_standing(tmp_path) -> None:
    """The same proof across independent databases, in case one shared them."""

    snapshots = []
    for name, value in (("worst", 1), ("best", 5)):
        directory = tmp_path / name
        directory.mkdir()
        with _client(directory) as client:
            _earn_some_competence(client)
            _rate_everything(client, value)
            snapshots.append(_competence_snapshot(client, drop_wall_clock=True))

    assert snapshots[0] == snapshots[1]


def test_feedback_does_not_move_the_capstone_or_advanced_standing(tmp_path) -> None:
    with _client(tmp_path) as client:
        before = client.get("/api/v1/progress").json()["advanced_standing"]
        _rate_everything(client, 5)
        # A learner who says they understood everything has still demonstrated
        # nothing. Self-report is not transfer.
        after = client.get("/api/v1/progress").json()["advanced_standing"]
        capstone = client.get("/api/v1/capstone").json()

    assert after == before
    assert after["advanced_competence_demonstrated"] is False
    assert capstone["status"] == "not_started"


def test_a_learner_who_gives_feedback_still_completes_normally(tmp_path) -> None:
    """Positive control: instrumentation must not break the thing it observes."""

    with _client(tmp_path) as client:
        _rate_everything_first = client.post(
            "/api/v1/feedback/modules/F0",
            json={
                "clarity": 2,
                "confidence": 1,
                "difficulty": "too_hard",
                "self_assessment": "still_confused",
                "comment": "lost me",
            },
        )
        assert _rate_everything_first.status_code == 200
        _earn_some_competence(client)
        progress = client.get("/api/v1/progress").json()

    module = next(item for item in progress["modules"] if item["module_id"] == "F0")
    assert module["status"] == "complete"
    assert progress["completed_modules"] >= 1
    assert progress["concepts_mastered"]


# --------------------------------------------------------------- structural
@pytest.mark.parametrize("relative", COMPETENCE_MODULES)
def test_competence_modules_do_not_import_the_feedback_feature(relative) -> None:
    """Direction of dependency, checked in the AST rather than by grep."""

    tree = ast.parse((SOURCE / relative).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    offending = {name for name in imported if "feedback" in name.lower()}
    assert not offending, f"{relative} imports feedback: {sorted(offending)}"


@pytest.mark.parametrize("relative", COMPETENCE_MODULES)
def test_competence_modules_never_read_a_feedback_table(relative) -> None:
    source = (SOURCE / relative).read_text(encoding="utf-8")
    for table in (
        "module_feedback",
        "course_feedback",
        "feedback_sessions",
        "feedback_sync_state",
        "feedback_consent_events",
    ):
        assert table not in source, f"{relative} references the {table} table"


def test_the_feedback_module_never_writes_to_a_learner_evidence_table() -> None:
    """Feedback may read the learner record. It may never write to it."""

    source = (SOURCE / "academy" / "feedback.py").read_text(encoding="utf-8")
    for table in ("module_progress", "assessment_attempts", "capstone_runs"):
        for statement in ("INSERT INTO", "UPDATE", "DELETE FROM", "ALTER TABLE", "DROP TABLE"):
            assert f"{statement} {table}" not in source, (
                f"feedback.py issues `{statement} {table}` — evidence must not be touched"
            )


def test_the_assessment_outcome_accessor_is_read_only(tmp_path) -> None:
    """The one method feedback calls on the learner record must not mutate it.

    Checked twice: the source contains no write statement, and calling it
    against a fresh database leaves that database byte-identical. The second
    check is the one that matters — the first would miss a write made through a
    helper.
    """

    source = (SOURCE / "academy" / "progress.py").read_text(encoding="utf-8")
    method = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "assessment_outcome"
    )
    # The docstring explains what the method deliberately does not do, so it
    # names the very things being searched for. Check the code, not the prose.
    statements = [
        node
        for node in method.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    code = "\n".join(ast.unparse(node) for node in statements)
    for statement in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "_ensure_row"):
        assert statement not in code, f"assessment_outcome performs a write ({statement})"

    database = tmp_path / "read-only.db"
    repository = SQLiteLearnerRecordRepository(database)
    before = database.read_bytes()
    assert repository.assessment_outcome("F0") == (ModuleStatus.NOT_STARTED, 0, None, None)
    assert database.read_bytes() == before, "describing a module changed the learner record"


# ------------------------------------------------------------- distributional
FORBIDDEN_CREDENTIAL_SYMBOLS = (
    "NORNYX_FEEDBACK_GITHUB_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "github_token",
    "ghp_",
    "github_pat_",
)


def _shipped_learner_files() -> list[Path]:
    files = [path for path in (SOURCE).rglob("*.py")]
    files += [path for path in (REPOSITORY / "frontend" / "src").rglob("*.ts")]
    files += [path for path in (REPOSITORY / "frontend" / "src").rglob("*.tsx")]
    files += [REPOSITORY / "Dockerfile", REPOSITORY / "compose.yaml", REPOSITORY / "pyproject.toml"]
    return [path for path in files if path.is_file()]


@pytest.mark.parametrize("symbol", FORBIDDEN_CREDENTIAL_SYMBOLS)
def test_no_github_credential_symbol_exists_in_the_learner_distribution(symbol) -> None:
    """A learner installation must contain zero maintainer GitHub authority.

    Not "an unset token" — no place to put one. The gateway is a separate
    distribution precisely so this can be checked mechanically.
    """

    offenders = [
        str(path.relative_to(REPOSITORY))
        for path in _shipped_learner_files()
        if symbol in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert not offenders, f"{symbol} appears in shipped learner files: {offenders}"


def test_the_learner_image_does_not_contain_the_gateway() -> None:
    """The Dockerfile copies an explicit path list. `gateway/` is not on it."""

    dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
    copied = [line for line in dockerfile.splitlines() if line.strip().startswith("COPY")]
    assert copied, "the Dockerfile no longer copies anything — re-check this invariant"
    assert not any("gateway" in line for line in copied), (
        "the production image copies the feedback gateway; the learner installation must not "
        "carry the component that holds GitHub authority"
    )
    ignored = (REPOSITORY / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert any(line.strip().rstrip("/") == "gateway" for line in ignored), (
        ".dockerignore must exclude gateway/ so no build context can pull it in"
    )


def test_the_academy_never_references_the_github_api() -> None:
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "api.github.com" not in text, f"{path} reaches for the GitHub API directly"


def test_no_production_feedback_endpoint_is_baked_into_the_product() -> None:
    """A URL nobody has deployed must not appear as if it were live."""

    for path in _shipped_learner_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for claim in ("feedback.nornyx.", "https://nornyx-feedback", "gateway.nornyx."):
            assert claim not in text, f"{path} hard-codes a feedback endpoint that does not exist"

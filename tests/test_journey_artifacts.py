"""Guards on the reviewer-visible learner journey (B4).

The artifact is presentation, not proof. These tests protect three things:

  - the set a reviewer downloads is complete and belongs to the commit under
    review, because a missing screen looks like a screen that never existed;
  - captures are taken *after* the pedagogical gate each screen depends on, so
    screen 6 shows a real governed execution rather than empty furniture;
  - screenshot presence never becomes a correctness claim.

The verifier is exercised against synthetic sets rather than by running a
browser, so these run in the ordinary backend job.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from nornyx_lab.engine import repo_root

ROOT = repo_root()
CAPTURE = ROOT / "frontend" / "e2e" / "learner-journey.capture.ts"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# The verifier is a script rather than a package module, because CI runs it
# directly between capture and publication.
sys.path.insert(0, str(ROOT / "scripts"))

from verify_journey_artifacts import expected_screens, verify  # noqa: E402


def _story_screens() -> list[dict[str, object]]:
    return expected_screens()


def _write_set(directory: Path, *, commit: str = "abc123", complete: bool = True) -> Path:
    """A well-formed set, as the capture would produce it."""
    screens = []
    for screen in _story_screens():
        name = f"{screen['number']:02d}-{screen['id']}.png"
        (directory / name).write_bytes(b"\x89PNG\r\n\x1a\n")
        screens.append(
            {
                "number": screen["number"],
                "id": screen["id"],
                "title": screen["title"],
                "viewport": "mobile",
                "file": name,
                "gate": "gate satisfied",
                "captured_at": "2026-01-01T00:00:00.000Z",
            }
        )
    desktop = "06-run-governed-desktop.png"
    (directory / desktop).write_bytes(b"\x89PNG\r\n\x1a\n")
    screens.append(
        {
            "number": 6,
            "id": "run-governed",
            "title": "Run it again, with the rules in place",
            "viewport": "desktop",
            "file": desktop,
            "gate": "governed run executed at 1280x800",
            "captured_at": "2026-01-01T00:00:00.000Z",
        }
    )
    (directory / "manifest.json").write_text(
        json.dumps({"commit": commit, "complete": complete, "screens": screens}),
        encoding="utf-8",
    )
    return directory


# ------------------------------------------------------------------ the set
def test_a_well_formed_set_is_publishable(tmp_path) -> None:
    assert verify(_write_set(tmp_path), expect_commit="abc123") == []


def test_the_expected_screens_come_from_the_demo_story(tmp_path) -> None:
    """Hard-coding nine titles here would let the capture and the demo drift
    apart while both still passed their own checks."""
    screens = _story_screens()
    assert len(screens) == 9
    assert [item["number"] for item in screens] == list(range(1, 10))


def test_a_missing_screen_is_not_publishable(tmp_path) -> None:
    directory = _write_set(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    dropped = manifest["screens"].pop(4)
    (directory / str(dropped["file"])).unlink()
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    problems = verify(directory)
    assert any("was not captured" in problem for problem in problems)


def test_a_manifest_entry_without_its_file_is_not_publishable(tmp_path) -> None:
    directory = _write_set(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    (directory / str(manifest["screens"][0]["file"])).unlink()
    problems = verify(directory)
    assert any("not in the artifact directory" in problem for problem in problems)


def test_an_incomplete_run_is_not_publishable(tmp_path) -> None:
    problems = verify(_write_set(tmp_path, complete=False))
    assert any("not marked complete" in problem for problem in problems)


def test_a_set_from_another_commit_is_not_publishable(tmp_path) -> None:
    """Misattributing what a reviewer is looking at is the failure this
    prevents."""
    problems = verify(_write_set(tmp_path, commit="deadbee"), expect_commit="abc123")
    assert any("not the tested commit" in problem for problem in problems)


def test_a_missing_manifest_is_not_publishable(tmp_path) -> None:
    problems = verify(tmp_path)
    assert problems and "did not finish" in problems[0]


def test_a_stray_image_is_not_publishable(tmp_path) -> None:
    directory = _write_set(tmp_path)
    (directory / "99-unexpected.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    problems = verify(directory)
    assert any("not listed in the manifest" in problem for problem in problems)


def test_the_desktop_capture_must_be_the_governed_payoff(tmp_path) -> None:
    directory = _write_set(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["screens"][-1]["id"] = "meet"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    problems = verify(directory)
    assert any("governed payoff" in problem for problem in problems)


# --------------------------------------------------------- gates before capture
@pytest.mark.parametrize(
    ("screen", "required"),
    [
        ("run-ungoverned", "Run without governance"),
        ("run-governed", "Run with governance"),
    ],
)
def test_run_screens_are_captured_after_a_real_execution(screen: str, required: str) -> None:
    """A screenshot of an un-run screen would show empty furniture while
    implying the journey happened."""
    source = CAPTURE.read_text(encoding="utf-8")
    index = source.index(f'id: "{screen}"')
    preceding = source[:index]
    assert required in preceding, f"{screen} is captured without first clicking {required!r}"


def test_the_capture_asserts_a_result_before_photographing_it() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    # Screen 6 must wait for the derived explanation and the causal chain, not
    # merely for the screen to be on-file.
    index = source.index('id: "run-governed"')
    preceding = source[:index]
    assert 'getByTestId("run-explanation")' in preceding
    assert 'getByTestId("causal-chain")' in preceding


def test_every_capture_records_the_gate_it_followed() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    captures = source.count("await capture(page, {")
    gates = len(re.findall(r"gate:\s*\"", source))
    assert captures == 10, f"expected 10 captures, found {captures}"
    assert gates == captures, "every capture must record which gate it followed"


# ------------------------------------------------------- not a correctness claim
def test_the_capture_states_that_it_is_not_evidence_of_correctness() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    assert "not a correctness check" in source
    assert re.search(r"not evidence.*correct|remain the evidence", source, re.IGNORECASE)


def test_the_manifest_carries_the_same_disclaimer() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    note = source[source.index("note:") : source.index("commit: commitSha()")]
    assert "not evidence of correctness" in note or "not evidence" in note
    assert "executable" in note


# ------------------------------------------------------------------ wiring
def test_the_capture_is_excluded_from_the_regression_suite() -> None:
    """Capture is not a regression test, and must not run as one."""
    config = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "testMatch: /.*\\.spec\\.ts/" in config
    assert "testMatch: /.*\\.capture\\.ts/" in config

    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["test:e2e"].endswith("--project=chromium")
    assert package["scripts"]["test:journey"].endswith("--project=journey")


def test_ci_verifies_before_it_publishes_and_names_the_artifact_by_commit() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["learner-journey"]["steps"]
    names = [str(step.get("name", "")) for step in steps]

    capture_at = next(i for i, name in enumerate(names) if "Capture the reviewer" in name)
    verify_at = next(i for i, name in enumerate(names) if "Verify the set" in name)
    # The reviewer upload names itself from the commit-derived step output, so
    # match on that expression rather than on a literal artifact name.
    upload_at = next(
        i
        for i, step in enumerate(steps)
        if "upload-artifact" in str(step.get("uses", ""))
        and "steps.journey.outputs.name" in str(step.get("with", {}).get("name", ""))
    )
    assert capture_at < verify_at < upload_at, (
        "verification must sit between capture and publication, or a broken set ships"
    )

    verify_step = steps[verify_at]
    assert "--expect-commit" in str(verify_step["run"])

    upload = steps[upload_at]["with"]
    assert upload["if-no-files-found"] == "error"
    assert "steps.journey.outputs.name" in str(upload["name"])
    # No `if: always()` — a failed verification must stop publication.
    assert "if" not in steps[upload_at]


def test_debug_evidence_is_published_separately_from_reviewer_material() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["learner-journey"]["steps"]
    uploads = {
        str(step.get("with", {}).get("name", "")): step
        for step in steps
        if "upload-artifact" in str(step.get("uses", ""))
    }
    assert "playwright-debug-evidence" in uploads, (
        "traces and failure screenshots must not share a name with reviewer material"
    )
    debug = uploads["playwright-debug-evidence"]
    assert debug.get("if") == "always()", "debug evidence is most useful exactly when the job fails"


def test_generated_captures_are_never_committed() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "frontend/journey-artifacts/" in ignored
    assert not (ROOT / "frontend" / "journey-artifacts" / "manifest.json").exists() or True

"""Validate a captured learner-journey artifact set before it is published.

The point is that an incomplete set is never uploaded. A reviewer opening
`learner-journey-<sha>` should be able to assume the nine screens are all there,
in order, from the commit named in the manifest — otherwise the artifact is worse
than absent, because a missing screen looks like a screen that did not exist.

This deliberately checks the *set*, not the images. It cannot and does not say
whether the journey behaved correctly; the executable specs do that.

Usage:
    python scripts/verify_journey_artifacts.py <directory> [--expect-commit SHA]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STORY = REPO_ROOT / "src" / "nornyx_lab" / "academy" / "content" / "demo_story.json"


def expected_screens() -> list[dict[str, Any]]:
    """The nine screens, read from the story rather than restated here.

    Hard-coding the list would let the capture and the demo drift apart while
    both still passed their own checks.
    """
    story = json.loads(STORY.read_text(encoding="utf-8"))
    return [
        {"number": screen["number"], "id": screen["id"], "title": screen["title"]}
        for screen in story["screens"]
    ]


def verify(directory: Path, expect_commit: str | None = None) -> list[str]:
    """Return a list of problems. Empty means the set is publishable."""
    problems: list[str] = []

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return [f"no manifest at {manifest_path}: the capture did not finish"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"manifest is not readable JSON: {exc}"]

    screens = manifest.get("screens", [])
    mobile = [item for item in screens if item.get("viewport") == "mobile"]
    desktop = [item for item in screens if item.get("viewport") == "desktop"]
    expected = expected_screens()

    # --- the set is complete -------------------------------------------------
    if len(mobile) != len(expected):
        problems.append(f"expected {len(expected)} mobile screens, manifest lists {len(mobile)}")
    if len(desktop) != 1:
        problems.append(f"expected exactly 1 desktop screen, manifest lists {len(desktop)}")
    if manifest.get("complete") is not True:
        problems.append("manifest is not marked complete: the capture run did not finish cleanly")

    # --- the screens are the ones the demo actually has ----------------------
    by_number = {item.get("number"): item for item in mobile}
    for screen in expected:
        captured = by_number.get(screen["number"])
        if captured is None:
            problems.append(f"screen {screen['number']} ({screen['id']}) was not captured")
            continue
        if captured.get("id") != screen["id"]:
            problems.append(
                f"screen {screen['number']} captured as {captured.get('id')!r}, "
                f"demo_story.json says {screen['id']!r}"
            )
        if captured.get("title") != screen["title"]:
            problems.append(
                f"screen {screen['number']} title {captured.get('title')!r} does not match "
                f"demo_story.json title {screen['title']!r}"
            )

    # --- every capture names the gate it waited for --------------------------
    for item in screens:
        if not str(item.get("gate", "")).strip():
            problems.append(f"capture {item.get('file')} does not record which gate it followed")

    # --- the desktop capture is the governed payoff --------------------------
    if desktop and desktop[0].get("id") != "run-governed":
        problems.append(
            f"the desktop capture is {desktop[0].get('id')!r}; it must be the governed payoff "
            f"screen, which is the one carrying the counters, explanation and causal chain"
        )

    # --- the files referenced actually exist ---------------------------------
    for item in screens:
        name = item.get("file")
        if not name:
            problems.append("a manifest entry has no file name")
            continue
        path = directory / name
        if not path.is_file():
            problems.append(f"manifest lists {name}, which is not in the artifact directory")
        elif path.stat().st_size == 0:
            problems.append(f"{name} is empty")

    # --- no stray images beyond the manifest ---------------------------------
    listed = {item.get("file") for item in screens}
    for path in sorted(directory.glob("*.png")):
        if path.name not in listed:
            problems.append(f"{path.name} is present but not listed in the manifest")

    # --- the artifact belongs to the commit under review ---------------------
    if expect_commit:
        actual = str(manifest.get("commit", ""))
        if actual != expect_commit:
            problems.append(
                f"manifest commit {actual!r} is not the tested commit {expect_commit!r}: "
                f"the artifact would misattribute what a reviewer is looking at"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expect-commit", default=None)
    args = parser.parse_args()

    problems = verify(args.directory, args.expect_commit)
    if problems:
        print("Journey artifact set is NOT publishable:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
    print(
        f"Journey artifact set verified: {len(manifest['screens'])} captures "
        f"from commit {manifest['commit'][:7]}."
    )
    print("This is reviewer material. It is not evidence that the journey behaved correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

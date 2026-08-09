"""Validate the governed/ungoverned counter semantics of a demo run.

Reads a `/api/v1/demo/run` response on stdin and decides whether the product
reported what the curriculum says it must:

    ungoverned  publish_external   1 / 1   executed
    governed    publish_external   0 / 0   prevented_before_execution

The conditional matters more than the numbers. Governed `0/0` is evidence of
prevention *only because* the same planned action demonstrably reaches the tool
as `1/1` on the ungoverned path. An action nobody planned also records `0/0`,
which is why the governed `meaning` is checked rather than the counts alone.

Three outcomes, deliberately distinct:

    0   the semantics hold
    1   the product reported something else, or something unusable
    4   this checker could not decide

The third is the one the first independent run needed and did not have. A crash
inside the instrument is not evidence about the product, and reporting it as
`product-failure` attributes a defect to the thing being measured. Note the
boundary: malformed or contract-violating *product output* is a product failure,
because emitting it is the product's job. Only a failure of this module's own
ability to decide is a verifier failure.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any

EXIT_OK = 0
EXIT_PRODUCT_FAILURE = 1
EXIT_VERIFIER_FAILURE = 4

ACTION = "publish_external"

EXPECTED = {
    "ungoverned": {"attempts": 1, "completions": 1, "meaning": "executed"},
    "governed": {"attempts": 0, "completions": 0, "meaning": "prevented_before_execution"},
}


class ProductContractError(Exception):
    """The response is not the shape the API documents.

    Raised for missing variants, missing counters, or fields of the wrong type.
    This is a *product* failure: producing a well-formed response is the
    service's responsibility, and hiding it as a verifier failure would let a
    real defect pass as an instrument problem.
    """


@dataclass
class Findings:
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _variant(payload: Any, variant_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProductContractError(f"the response is {type(payload).__name__}, not an object")
    variants = payload.get("variants")
    if not isinstance(variants, list):
        raise ProductContractError("the response has no 'variants' list")
    for variant in variants:
        if isinstance(variant, dict) and variant.get("id") == variant_id:
            return variant
    raise ProductContractError(f"the response contains no '{variant_id}' variant")


def _counter(variant: dict[str, Any], variant_id: str) -> dict[str, Any]:
    counters = variant.get("counters")
    if not isinstance(counters, list):
        raise ProductContractError(f"the '{variant_id}' variant has no 'counters' list")
    for counter in counters:
        if isinstance(counter, dict) and counter.get("action") == ACTION:
            return counter
    raise ProductContractError(f"the '{variant_id}' variant has no '{ACTION}' counter")


def evaluate(payload: Any) -> Findings:
    """Compare a demo response against the documented semantics.

    Raises `ProductContractError` when the response cannot be read as the API
    documents it. Returns findings — possibly with problems — when it can.
    """
    findings = Findings()
    observed: dict[str, dict[str, Any]] = {}

    for variant_id, expected in EXPECTED.items():
        counter = _counter(_variant(payload, variant_id), variant_id)
        attempts = counter.get("attempts")
        completions = counter.get("completions")
        meaning = counter.get("meaning")

        if not isinstance(attempts, int) or not isinstance(completions, int):
            raise ProductContractError(
                f"the '{variant_id}' {ACTION} counter has non-integer attempts/completions: "
                f"{attempts!r}/{completions!r}"
            )

        observed[variant_id] = {
            "attempts": attempts,
            "completions": completions,
            "meaning": meaning,
        }
        findings.lines.append(f"{variant_id:<10} {ACTION}: {attempts}/{completions} ({meaning})")

        if attempts != expected["attempts"] or completions != expected["completions"]:
            findings.problems.append(
                f"{variant_id} recorded {attempts}/{completions}, expected "
                f"{expected['attempts']}/{expected['completions']}"
            )
        if meaning != expected["meaning"]:
            findings.problems.append(
                f"{variant_id} meaning is {meaning!r}, expected {expected['meaning']!r}"
            )

    # State the conditional explicitly, so a reader of the evidence sees why the
    # governed zeros are being read as prevention rather than as absence.
    if findings.ok:
        findings.lines.append(
            "0/0 is interpretable as prevention: the same plan recorded 1/1 without governance"
        )
    elif observed.get("ungoverned", {}).get("completions") != 1:
        findings.problems.append(
            "the ungoverned path did not complete the action, so a governed 0/0 would not "
            "distinguish prevention from an action that was never planned"
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        raw = sys.stdin.read()
    except Exception as exc:  # pragma: no cover - stdin is provided by the caller
        print(f"VERIFIER ERROR: could not read the response: {exc}")
        return EXIT_VERIFIER_FAILURE

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        # The service produced something that is not JSON. That is the product's
        # failure, not this checker's.
        print(f"PRODUCT PROBLEM: the response is not valid JSON: {exc}")
        return EXIT_PRODUCT_FAILURE

    try:
        findings = evaluate(payload)
    except ProductContractError as exc:
        print(f"PRODUCT PROBLEM: {exc}")
        return EXIT_PRODUCT_FAILURE
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see module docstring
        print(f"VERIFIER ERROR: {type(exc).__name__}: {exc}")
        return EXIT_VERIFIER_FAILURE

    for line in findings.lines:
        print(line)
    for problem in findings.problems:
        print(f"PRODUCT PROBLEM: {problem}")

    return EXIT_OK if findings.ok else EXIT_PRODUCT_FAILURE


if __name__ == "__main__":
    sys.exit(main())

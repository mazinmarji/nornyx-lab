"""Unit tests for the packaged counter-semantics validator.

These execute the real validator — the same code the production image runs —
rather than asserting that a shell string contains the right words. That
distinction is the whole point of this module existing: the previous checker was
a Python program inside a shell argument, and every test around it exercised the
wrapper while the payload was never run in the form production used.

The classification boundary is what most of these pin down. Malformed *product
output* is a product failure, because emitting a well-formed response is the
service's job. A verifier failure means this module could not decide.
"""

from __future__ import annotations

import io
import json

import pytest

from nornyx_lab.verification.check_counters import (
    EXIT_OK,
    EXIT_PRODUCT_FAILURE,
    EXIT_VERIFIER_FAILURE,
    ProductContractError,
    evaluate,
    main,
)


def _counter(action: str, attempts: int, completions: int, meaning: str) -> dict:
    return {
        "action": action,
        "attempts": attempts,
        "completions": completions,
        "meaning": meaning,
    }


def _response(
    *,
    ungoverned=(1, 1, "executed"),
    governed=(0, 0, "prevented_before_execution"),
    include_action: bool = True,
) -> dict:
    def counters(values):
        rows = [_counter("search_web", 1, 1, "executed")]
        if include_action:
            rows.append(_counter("publish_external", *values))
        return rows

    return {
        "run_id": "test",
        "variants": [
            {"id": "ungoverned", "counters": counters(ungoverned)},
            {"id": "governed", "counters": counters(governed)},
        ],
    }


def _run_main(payload, monkeypatch) -> tuple[int, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    import contextlib

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main()
    return code, buffer.getvalue()


# ------------------------------------------------------------------ the good case
def test_the_documented_semantics_pass() -> None:
    findings = evaluate(_response())
    assert findings.ok, findings.problems
    assert any("1/1" in line for line in findings.lines)
    assert any("0/0" in line for line in findings.lines)


def test_the_valid_case_states_why_zero_zero_counts_as_prevention() -> None:
    """The conditional is the lesson; the evidence should carry it."""
    findings = evaluate(_response())
    assert any("interpretable as prevention" in line for line in findings.lines)
    assert any("1/1 without governance" in line for line in findings.lines)


def test_main_exits_zero_on_the_documented_semantics(monkeypatch) -> None:
    code, output = _run_main(_response(), monkeypatch)
    assert code == EXIT_OK
    assert "PRODUCT PROBLEM" not in output


# ------------------------------------------------------- product-semantic failures
def test_a_wrong_ungoverned_count_is_a_product_failure(monkeypatch) -> None:
    code, output = _run_main(_response(ungoverned=(1, 0, "attempted_not_completed")), monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "ungoverned recorded 1/0" in output


def test_a_wrong_governed_count_is_a_product_failure(monkeypatch) -> None:
    code, output = _run_main(_response(governed=(1, 1, "executed")), monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "governed recorded 1/1" in output


def test_governed_zero_zero_with_the_wrong_meaning_fails(monkeypatch) -> None:
    """The number-only check would pass this, and it must not.

    `not_planned` is also 0/0. Reading it as prevention is the exact overclaim
    the curriculum exists to teach against.
    """
    code, output = _run_main(_response(governed=(0, 0, "not_planned")), monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "not_planned" in output
    assert "prevented_before_execution" in output


def test_an_ungoverned_path_that_never_ran_cannot_support_a_prevention_claim() -> None:
    findings = evaluate(_response(ungoverned=(0, 0, "not_planned")))
    assert not findings.ok
    assert any(
        "never planned" in problem or "not distinguish" in problem for problem in findings.problems
    )


# --------------------------------------------------- contract failures are product
def test_a_missing_publish_counter_is_a_product_failure_not_a_crash(monkeypatch) -> None:
    """A response without the action is the service failing to report it."""
    code, output = _run_main(_response(include_action=False), monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "publish_external" in output
    assert "VERIFIER ERROR" not in output


def test_a_missing_variant_is_a_product_failure(monkeypatch) -> None:
    payload = _response()
    payload["variants"] = [payload["variants"][0]]
    code, output = _run_main(payload, monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "governed" in output


def test_a_response_without_variants_is_a_product_failure(monkeypatch) -> None:
    code, output = _run_main({"run_id": "x"}, monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "variants" in output


def test_non_json_output_is_a_product_failure(monkeypatch) -> None:
    code, output = _run_main("<html>gateway timeout</html>", monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "not valid JSON" in output


def test_non_integer_counters_are_a_product_failure(monkeypatch) -> None:
    payload = _response()
    payload["variants"][0]["counters"][1]["attempts"] = "one"
    code, output = _run_main(payload, monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE
    assert "non-integer" in output


@pytest.mark.parametrize("payload", [[], "null", 42])
def test_a_response_of_the_wrong_type_is_a_product_failure(payload, monkeypatch) -> None:
    code, _ = _run_main(payload, monkeypatch)
    assert code == EXIT_PRODUCT_FAILURE


# ----------------------------------------------- only instrument faults are verifier
def test_an_internal_fault_is_a_verifier_failure_not_a_product_failure(monkeypatch) -> None:
    """The distinction the first independent run needed and did not have.

    A bug inside the checker says nothing about the product. Reporting it as a
    product failure attributes a defect to the thing being measured — which is
    precisely what happened when the shell mangled the old inline program.
    """
    import nornyx_lab.verification.check_counters as module

    def explode(_payload):
        raise RuntimeError("simulated fault inside the instrument")

    monkeypatch.setattr(module, "evaluate", explode)
    code, output = _run_main(_response(), monkeypatch)

    assert code == EXIT_VERIFIER_FAILURE
    assert "VERIFIER ERROR" in output
    assert "RuntimeError" in output
    assert "PRODUCT PROBLEM" not in output


def test_a_contract_error_raised_internally_stays_a_product_failure(monkeypatch) -> None:
    """The escape hatch must not swallow genuine product defects."""
    import nornyx_lab.verification.check_counters as module

    def contract_error(_payload):
        raise ProductContractError("the response omitted something required")

    monkeypatch.setattr(module, "evaluate", contract_error)
    code, output = _run_main(_response(), monkeypatch)

    assert code == EXIT_PRODUCT_FAILURE
    assert "PRODUCT PROBLEM" in output
    assert "VERIFIER ERROR" not in output


def test_the_three_exit_codes_are_distinct() -> None:
    assert len({EXIT_OK, EXIT_PRODUCT_FAILURE, EXIT_VERIFIER_FAILURE}) == 3
    assert EXIT_VERIFIER_FAILURE == 4

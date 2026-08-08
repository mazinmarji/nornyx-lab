"""Remediation guidance: coverage, honesty, and the limits of a hint.

Guidance text is authored, because diagnostic semantics are stable code-level
knowledge. Whether a correction worked is never authored — it is observed from a
re-run. These tests hold that line in three ways:

  - every diagnostic code the academy can actually surface has an entry, found by
    exercising the learner-reachable flows rather than by reading source;
  - no entry claims an outcome, and every entry says how to verify;
  - following a correction produces a fresh observation, not a resolution.

The last one is the point of the whole feature. A hint that reads as "do this and
you are done" is the same category of overclaim as "the AI said it refused": an
intention standing in for evidence of an outcome.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.pedagogy import UNKNOWN_CODE_NOTICE, PedagogyRepository

FIVE_PARTS = ("title", "means", "matters", "inspect", "correction", "verify")


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
        )
    )


@pytest.fixture(scope="module")
def registry() -> PedagogyRepository:
    return PedagogyRepository()


def _demo_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "injection_enabled": True,
        "enforcement_enabled": True,
        "enforcement_failure": False,
        "failure_mode": "fail_closed",
        "identity_ref": "identity.research_assistant",
        "observed_subject_revision": None,
        "approval_state": "missing",
        "planner_mode": "deterministic",
    }
    payload.update(overrides)
    return payload


def _diagnostic_codes(payload: object) -> set[str]:
    """Codes that reach a learner as diagnostics, not as policy decisions.

    A decision code like CAPABILITY_DENIED is a correct outcome being reported,
    not a problem to remediate, so offering it a "correction" would be wrong.
    Only `diagnostics` and `findings` collections are in scope.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("diagnostics", "findings") and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and isinstance(item.get("code"), str):
                            found.add(item["code"])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


# ------------------------------------------------------------------- shape
def test_every_entry_carries_all_five_parts(registry) -> None:
    for entry in registry.remediation().entries:
        for field in FIVE_PARTS:
            assert getattr(entry, field).strip(), f"{entry.code} has an empty {field}"


def test_no_entry_claims_an_outcome(registry) -> None:
    """Authored text may not assert that anything is fixed.

    Nothing verifies authored prose, so a hint saying "this resolves the issue"
    would be an unverified claim about behaviour sitting directly beside a real
    diagnostic — the precise overclaim this curriculum teaches against.
    """
    banned = re.compile(
        r"\b("
        r"(this|that|it)\s+(fixes|resolves|solves|corrects)"
        r"|will\s+(fix|resolve|solve|prevent|ensure|guarantee)"
        r"|is\s+now\s+(safe|fixed|resolved|secure|correct)"
        r"|(guarantees|ensures)\s+that"
        r"|problem\s+solved"
        r"|no\s+longer\s+(a\s+)?(risk|an?\s+issue)"
        r")\b",
        re.IGNORECASE,
    )
    for entry in registry.remediation().entries:
        for field in FIVE_PARTS:
            text = getattr(entry, field)
            hit = banned.search(text)
            assert not hit, f"{entry.code}.{field} claims an outcome: {hit.group(0)!r}"


def test_every_entry_says_how_to_verify(registry) -> None:
    """The fifth part is the one that makes the other four safe to read."""
    reverify = re.compile(
        r"\b(re-?run|re-?check|re-?apply|regenerate|compare|confirm|observe|read)\b",
        re.IGNORECASE,
    )
    for entry in registry.remediation().entries:
        assert reverify.search(entry.verify), (
            f"{entry.code}.verify does not name anything to re-run or observe: {entry.verify!r}"
        )


def test_guidance_is_labelled_as_academy_material(registry) -> None:
    """A hint beside a Nornyx code is exactly where provenance gets assumed."""
    payload = registry.remediation()
    assert "Academy" in payload.provenance_label
    assert payload.unknown_code_notice == UNKNOWN_CODE_NOTICE


# ------------------------------------------------------------------ coverage
def test_every_learner_reachable_diagnostic_has_guidance(tmp_path) -> None:
    """Coverage measured by exercising the academy, not by reading its source.

    Codes arrive dynamically — Nornyx diagnostics pass straight through — so a
    static scan would miss exactly the ones a learner is most likely to hit.
    """
    known = {entry.code for entry in PedagogyRepository().remediation().entries}
    observed: set[str] = set()

    with _client(tmp_path) as client:
        for contract_id in ("atlas", "ledger"):
            observed |= _diagnostic_codes(client.get(f"/api/v1/contracts/{contract_id}").json())

        mutations = [
            # Rejected edits: the workbench's own diagnostics.
            [
                {
                    "operation": "toggle_identity_capability",
                    "target": "identity.research_assistant",
                    "value": {"capability": "not_a_capability", "enabled": True},
                }
            ],
            [{"operation": "set_approval_expiry", "target": "gate.nope", "value": "P400D"}],
            [{"operation": "set_profile", "target": "profile", "value": "not_a_profile"}],
            [
                {
                    "operation": "remove_construct",
                    "target": "identity.research_assistant",
                    "value": None,
                }
            ],
            [
                {
                    "operation": "set_zone_share_category",
                    "target": "zone.public_web",
                    "value": "nope",
                }
            ],
            # Accepted edits that then fail Nornyx's own checks. These are the
            # two the Diagnostics page offers as buttons, so they are as
            # learner-reachable as anything in the product — and they surfaced
            # seven codes that the rejected-edit cases above never reach.
            [
                {
                    "operation": "set_subject_revision",
                    "target": "governance_evidence.subject_revision",
                    "value": f"git:{'f' * 40}",
                }
            ],
            [
                {
                    "operation": "remove_evidence_field",
                    "target": "approval_record",
                    "value": "content_hash",
                }
            ],
        ]
        for contract_id in ("atlas", "ledger"):
            for mutation in mutations:
                response = client.post(
                    "/api/v1/contracts/workbench",
                    json={"contract_id": contract_id, "mutations": mutation},
                )
                observed |= _diagnostic_codes(response.json())

        for overrides in (
            {},
            {"injection_enabled": False},
            {"enforcement_enabled": False},
            {"enforcement_failure": True, "failure_mode": "fail_open"},
            {"enforcement_failure": True, "failure_mode": "fail_closed"},
            {"enforcement_failure": True, "failure_mode": "bounded"},
            {"approval_state": "valid"},
            {"approval_state": "expired"},
            {"observed_subject_revision": "does-not-match"},
        ):
            response = client.post("/api/v1/demo/run", json=_demo_payload(**overrides))
            observed |= _diagnostic_codes(response.json())

    assert observed, "the sweep exercised nothing — the flows above stopped producing diagnostics"
    missing = sorted(observed - known)
    assert not missing, (
        f"diagnostic codes a learner can reach with no remediation guidance: {missing}. "
        f"Add them to content/remediation.json."
    )


def test_an_unregistered_code_is_not_guessed_at(registry) -> None:
    """Inventing guidance from the shape of a name is the failure mode itself."""
    assert registry.remediation_for("NOT_A_REAL_CODE_XYZ") is None
    assert registry.remediation_for("CAPABILITY_DENIED_LOOKALIKE") is None


def test_the_registry_is_served_and_grows_without_a_contract_change(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/remediation")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert body["unknown_code_notice"] == UNKNOWN_CODE_NOTICE
    # Codes live in `entries`, so adding one is data, not a schema change.
    assert isinstance(body["entries"], list) and body["entries"]
    assert {"code", *FIVE_PARTS} <= set(body["entries"][0])


# ------------------------------------------------------------------ negative
def test_following_a_correction_does_not_mark_the_diagnostic_resolved(tmp_path) -> None:
    """The one that matters.

    ENFORCEMENT_DISABLED tells the learner to enable the enforcement point. So
    enable it — and leave a second thing wrong. If guidance implied resolution,
    the re-run would come back clean because the instruction was obeyed. It does
    not: it comes back with a *different* observed failure and a completed
    publish, because the state of the world is read from the run, never inferred
    from having followed advice.
    """
    with _client(tmp_path) as client:
        disabled = client.post(
            "/api/v1/demo/run", json=_demo_payload(enforcement_enabled=False)
        ).json()
        assert "ENFORCEMENT_DISABLED" in _diagnostic_codes(disabled)

        # Apply the stated correction, with an unrelated fault still present.
        corrected = client.post(
            "/api/v1/demo/run",
            json=_demo_payload(
                enforcement_enabled=True, enforcement_failure=True, failure_mode="fail_open"
            ),
        ).json()

    codes = _diagnostic_codes(corrected)
    assert "ENFORCEMENT_DISABLED" not in codes, "the correction should change what is observed"
    assert codes, "a re-run must still report what it observed, not fall silent"

    governed = next(variant for variant in corrected["variants"] if variant["id"] == "governed")
    publication = next(
        counter for counter in governed["counters"] if counter["action"] == "publish_external"
    )
    # Following the advice did not prevent anything: fail-open let the tool run.
    assert publication["completions"] == 1, (
        "the corrected run must be judged on what it did, not on the correction being applied"
    )
    assert publication["meaning"] != "prevented_before_execution"


def test_no_response_field_reports_a_diagnostic_as_resolved(tmp_path) -> None:
    """There is no 'resolved' flag anywhere, and there must not be one.

    A boolean the UI could latch onto would let a hint be rendered as a verdict,
    which is what the five-part shape exists to prevent.
    """
    with _client(tmp_path) as client:
        remediation = client.get("/api/v1/remediation").json()
        run = client.post("/api/v1/demo/run", json=_demo_payload(enforcement_enabled=False)).json()

    banned_keys = {"resolved", "fixed", "remediated", "is_resolved", "remediation_applied"}
    for payload, label in ((remediation, "remediation registry"), (run, "scenario run")):

        def walk(node: object, label: str = label) -> None:
            if isinstance(node, dict):
                overlap = banned_keys & set(node)
                assert not overlap, f"{label} exposes a resolution flag: {sorted(overlap)}"
                for value in node.values():
                    walk(value, label)
            elif isinstance(node, list):
                for item in node:
                    walk(item, label)

        walk(payload)

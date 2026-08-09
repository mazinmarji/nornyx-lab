"""Capstone competence: scaffolding honesty, authorship, transfer, advanced gate.

The defect these tests pin down: a Guided capstone run — where the academy
supplies roles, identities, capabilities, zones, coordination, policy, and the
assurance claim — could stand in for independent advanced competence. Advanced
standing must instead require learner-authored governance decisions plus a
transfer of the model to a scenario that is not the guided default.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.assessments import AssessmentService
from nornyx_lab.academy.capstone import CapstoneInputError, capstone_template, run_capstone

DISBURSEMENT_ROLES = [
    {
        "id": "intake",
        "role": "intake lead",
        "identity_ref": "identity.intake_agent",
        "capability_ref": "read_customer_case",
        "action": "read_case",
    },
    {
        "id": "analysis",
        "role": "case analyst",
        "identity_ref": "identity.case_analyst",
        "capability_ref": "analyze_case",
        "action": "analyze_case",
    },
    {
        "id": "proposal",
        "role": "refund proposer",
        "identity_ref": "identity.case_analyst",
        "capability_ref": "propose_refund",
        "action": "propose_refund",
    },
    {
        "id": "approval-route",
        "role": "approval router",
        "identity_ref": "identity.compliance_officer",
        "capability_ref": "request_human_approval",
        "action": "request_approval",
    },
    {
        "id": "disbursement",
        "role": "refund disburser",
        "identity_ref": "identity.remediation_agent",
        "capability_ref": "issue_refund",
        "action": "issue_refund",
    },
    {
        "id": "closure",
        "role": "case owner",
        "identity_ref": "identity.compliance_officer",
        "capability_ref": "close_case",
        "action": "close_case",
    },
]

INDEPENDENT_DISBURSEMENT = {
    "framework": "framework-neutral",
    "failure_injection": "expired-approval",
    "scaffolding": "independent",
    "scenario": "refund-disbursement",
    "roles": DISBURSEMENT_ROLES,
    "coordination": {
        "delegation_id": "delegation.refund_proposal",
        "handoff_id": "handoff.compliance_closure",
        "require_delegation": True,
        "require_handoff": True,
    },
    "policy": {
        "approval_mode": "missing",
        "require_external_approval": True,
        "require_handoff_approval": True,
        "require_integrity_preflight": True,
    },
    "assurance": {
        "claim": (
            "On the named cooperative disbursement path, the selected synchronous "
            "surface applies a real Nornyx capability decision and human refund "
            "approval before the inert issue_refund callable."
        ),
        "residual_risk": (
            "Direct-call bypass of the disbursement callable remains possible, and "
            "Nornyx does not authenticate the approver or control credentials and "
            "network egress."
        ),
        "falsification_condition": (
            "Falsify this claim if the named issue_refund callable completes without "
            "the preceding capability and approval decisions on the selected surface."
        ),
    },
}


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(database_path=tmp_path / "capstone.db", frontend_dist=tmp_path))


def _complete_capstone_content(client: TestClient) -> None:
    """Execute the guided capstone and pass its assessment (content completion)."""

    run = client.post("/api/v1/capstone/run", json={"framework": "framework-neutral"})
    assert run.status_code == 200
    assert run.json()["completion_eligible"] is True
    definition = AssessmentService().definition("assessment.24")
    submitted = client.post(
        "/api/v1/assessments/assessment.24/submit",
        json={"answers": list(definition.correct)},
    )
    assert submitted.status_code == 200
    assert submitted.json()["passed"] is True


# ------------------------------------------------------------ guided honesty


def test_guided_run_is_labeled_scaffolded_and_does_not_grant_advanced(tmp_path) -> None:
    client = _client(tmp_path)
    _complete_capstone_content(client)

    progress = client.get("/api/v1/progress").json()
    assert progress["capstone_status"] == "complete", "content completion must still work"

    standing = progress["advanced_standing"]
    assert standing is not None
    assert standing["capstone_content_complete"] is True
    assert standing["independent_authorship_demonstrated"] is False
    assert standing["transfer_demonstrated"] is False
    assert standing["advanced_competence_demonstrated"] is False


def test_guided_result_describes_the_design_as_academy_provided() -> None:
    run = run_capstone({"scaffolding": "guided"})
    competence = run.results["competence"]
    assert competence["scaffolding"] == "guided"
    assert competence["learner_authored"] is False
    assert competence["counts_toward_advanced"] is False

    design_block = next(block for block in run.blocks if block.id == "capstone-design")
    text = f"{design_block.title} {design_block.body}".lower()
    assert "academy" in text or "scaffold" in text
    assert "learner-authored" not in (design_block.title or "").lower()


# ------------------------------------------------------------- authorship


def test_independent_scaffolding_requires_explicit_authoring() -> None:
    with pytest.raises(CapstoneInputError, match="independent"):
        run_capstone({"scaffolding": "independent"})

    partial = dict(INDEPENDENT_DISBURSEMENT)
    del partial["assurance"]
    with pytest.raises(CapstoneInputError, match="assurance"):
        run_capstone(partial)


def test_reduced_scaffolding_requires_roles_and_policy() -> None:
    with pytest.raises(CapstoneInputError, match="reduced"):
        run_capstone({"scaffolding": "reduced"})


# ---------------------------------------------------------------- transfer


def test_transfer_scenario_rejects_the_guided_default_design() -> None:
    """Pasting the guided remediation defaults into the transfer scenario fails.

    The transfer competence test would be meaningless if reproducing the guided
    Northstar defaults satisfied it.
    """

    guided = run_capstone({"scaffolding": "guided"})
    default_roles = guided.results["configuration"]["roles"]

    transferred = run_capstone(
        {
            **INDEPENDENT_DISBURSEMENT,
            "roles": default_roles,
        }
    )
    assert transferred.results["design_review"]["valid"] is False
    assert transferred.completion_eligible is False


def test_transfer_scenario_has_a_different_consequential_boundary() -> None:
    template = capstone_template()
    scenarios = {scenario.id: scenario for scenario in template.scenarios}
    assert set(scenarios) == {"customer-remediation", "refund-disbursement"}
    assert (
        scenarios["customer-remediation"].consequential_action
        != scenarios["refund-disbursement"].consequential_action
    )


def test_independent_transfer_design_is_completable_and_deterministic() -> None:
    first = run_capstone(INDEPENDENT_DISBURSEMENT)
    second = run_capstone(INDEPENDENT_DISBURSEMENT)

    assert first.completion_eligible is True
    assert first.results["competence"]["learner_authored"] is True
    assert first.results["competence"]["counts_toward_advanced"] is True
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


# ------------------------------------------------------------ advanced gate


def test_advanced_standing_requires_content_authorship_and_transfer(tmp_path) -> None:
    client = _client(tmp_path)
    _complete_capstone_content(client)

    response = client.post("/api/v1/capstone/run", json=INDEPENDENT_DISBURSEMENT)
    assert response.status_code == 200
    body = response.json()
    assert body["completion_eligible"] is True

    standing = client.get("/api/v1/progress").json()["advanced_standing"]
    assert standing["capstone_content_complete"] is True
    assert standing["capstone_concepts_demonstrated"] is True
    assert standing["independent_authorship_demonstrated"] is True
    assert standing["transfer_demonstrated"] is True
    assert standing["advanced_competence_demonstrated"] is True


def test_failed_independent_run_grants_no_advanced_credit(tmp_path) -> None:
    client = _client(tmp_path)

    broken = {
        **INDEPENDENT_DISBURSEMENT,
        "roles": [
            {
                **DISBURSEMENT_ROLES[0],
                "capability_ref": "issue_refund",  # intake agent does not hold this
            },
            *DISBURSEMENT_ROLES[1:],
        ],
    }
    response = client.post("/api/v1/capstone/run", json=broken)
    assert response.status_code == 200
    assert response.json()["completion_eligible"] is False

    standing = client.get("/api/v1/progress").json()["advanced_standing"]
    assert standing["independent_authorship_demonstrated"] is False
    assert standing["advanced_competence_demonstrated"] is False

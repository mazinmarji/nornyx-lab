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


# ------------------------------------------------- review-found regressions


@pytest.mark.parametrize("section", ["roles", "coordination", "policy", "assurance"])
def test_empty_object_sections_are_not_learner_authorship(section: str) -> None:
    """`{}` (or `[]`) is nothing supplied, not an authored design section.

    Review finding: Independent mode only checked for None, so `policy: {}`
    was silently filled with academy defaults while being credited as learner
    authorship. Empty containers must be rejected exactly like omissions.
    """

    config = {**INDEPENDENT_DISBURSEMENT, section: [] if section == "roles" else {}}
    with pytest.raises(CapstoneInputError, match="independent"):
        run_capstone(config)


def test_empty_trust_zones_object_is_not_authorship_on_remediation() -> None:
    remediation = {
        **INDEPENDENT_DISBURSEMENT,
        "scenario": "customer-remediation",
        "trust_zones": {},
    }
    with pytest.raises(CapstoneInputError, match="trust_zones"):
        run_capstone(remediation)


def test_guided_empty_objects_still_count_as_academy_defaults() -> None:
    """Even in Guided mode, `{}` must be recorded as defaults, never authorship."""

    run = run_capstone({"scaffolding": "guided", "policy": {}, "coordination": {}})
    competence = run.results["competence"]
    assert "policy" in competence["defaults_used"]
    assert "coordination" in competence["defaults_used"]
    assert competence["learner_authored"] is False


def test_incomplete_workflow_is_rejected_as_a_design_defect() -> None:
    """Omitting analysis/proposal/approval/closure must not stay eligible.

    Review finding: the design review validated only the steps that were
    supplied, so a two-step design (read the case, issue the refund) could
    potentially earn advanced evidence despite skipping the workflow stages
    the scenario exists to govern.
    """

    truncated = {
        **INDEPENDENT_DISBURSEMENT,
        "roles": [DISBURSEMENT_ROLES[0], DISBURSEMENT_ROLES[4]],
    }
    run = run_capstone(truncated)

    checks = run.results["design_review"]["checks"]
    assert checks["required_workflow_actions_covered"] is False
    assert run.results["design_review"]["valid"] is False
    assert run.completion_eligible is False
    assert run.results["competence"]["counts_toward_advanced"] is False


def test_complete_explicitly_authored_workflow_remains_eligible() -> None:
    """The positive control: full authorship still passes the tightened gates."""

    run = run_capstone(INDEPENDENT_DISBURSEMENT)
    assert run.results["design_review"]["checks"]["required_workflow_actions_covered"] is True
    assert run.completion_eligible is True


# --------------------------------------------- partial-authorship regressions


def test_partial_policy_is_not_learner_authorship_in_independent() -> None:
    """A one-field policy must not be credited as an authored policy.

    Review finding: non-empty sections counted as fully authored while the
    parsers silently defaulted every omitted field, so `policy:
    {"approval_mode": "missing"}` earned authorship credit for four decisions
    the learner made one of.
    """

    config = {**INDEPENDENT_DISBURSEMENT, "policy": {"approval_mode": "missing"}}
    with pytest.raises(CapstoneInputError, match="field-complete policy"):
        run_capstone(config)


def test_partial_coordination_is_not_learner_authorship_in_independent() -> None:
    config = {**INDEPENDENT_DISBURSEMENT, "coordination": {"require_delegation": True}}
    with pytest.raises(CapstoneInputError, match="field-complete coordination"):
        run_capstone(config)


def test_partial_trust_zones_are_not_learner_authorship_on_remediation() -> None:
    config = {
        **INDEPENDENT_DISBURSEMENT,
        "scenario": "customer-remediation",
        "trust_zones": {"source_zone": "zone.remediation_internal"},
    }
    with pytest.raises(CapstoneInputError, match="field-complete trust_zones"):
        run_capstone(config)


def test_reduced_policy_must_also_be_field_complete() -> None:
    """Reduced's contract says the learner authored the policy — all of it."""

    config = {
        "scaffolding": "reduced",
        "scenario": "refund-disbursement",
        "roles": DISBURSEMENT_ROLES,
        "policy": {"approval_mode": "missing"},
    }
    with pytest.raises(CapstoneInputError, match="field-complete policy"):
        run_capstone(config)


def test_explicit_null_never_silently_becomes_a_default() -> None:
    """`null` on a non-nullable field is rejected, not replaced."""

    config = {
        **INDEPENDENT_DISBURSEMENT,
        "policy": {**INDEPENDENT_DISBURSEMENT["policy"], "require_external_approval": None},
    }
    with pytest.raises(CapstoneInputError, match="must not be null"):
        run_capstone(config)


def test_explicit_null_coordination_refs_are_preserved_learner_decisions() -> None:
    """Where null IS a legitimate decision, the learner's null survives.

    Declaring no delegation and no handoff is a real governance choice; it
    must reach the run as None, never be swapped for the academy's declared
    default refs.
    """

    config = {
        **INDEPENDENT_DISBURSEMENT,
        "coordination": {
            "delegation_id": None,
            "handoff_id": None,
            "require_delegation": False,
            "require_handoff": False,
        },
    }
    run = run_capstone(config)

    coordination = run.results["configuration"]["coordination"]
    assert coordination["delegation_id"] is None
    assert coordination["handoff_id"] is None
    assert run.results["design_review"]["checks"]["delegation_choice_complete"] is True
    assert run.results["design_review"]["checks"]["handoff_choice_complete"] is True


def test_fully_explicit_independent_design_remains_the_positive_control() -> None:
    run = run_capstone(INDEPENDENT_DISBURSEMENT)
    assert run.completion_eligible is True
    assert run.results["competence"]["learner_authored"] is True
    # The disbursement scenario has no zone crossing, so trust_zones is the
    # one section legitimately left to the (unused) academy default.
    assert run.results["competence"]["defaults_used"] == ["trust_zones"]

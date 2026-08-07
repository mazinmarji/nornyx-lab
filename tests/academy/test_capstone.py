"""Focused checks for the learner-authored governed capstone."""

from __future__ import annotations

import hashlib

import pytest

from nornyx_lab.academy.capstone import (
    CapstoneConfig,
    CapstoneInputError,
    capstone_template,
    run_capstone,
)
from nornyx_lab.academy.schemas import CapstoneDefinition, StructuredLabRun
from nornyx_lab.contract import shared_contract


def _variant(run: StructuredLabRun, variant_id: str) -> dict:
    return next(item for item in run.results["variants"] if item["id"] == variant_id)


def _roles(*, notification_identity: str = "identity.remediation_agent") -> list[dict[str, str]]:
    return [
        {
            "id": "triage",
            "role": "learner named triage owner",
            "identity_ref": "identity.intake_agent",
            "capability_ref": "read_customer_case",
            "action": "read_case",
        },
        {
            "id": "investigate",
            "role": "learner named investigator",
            "identity_ref": "identity.case_analyst",
            "capability_ref": "analyze_case",
            "action": "analyze_case",
        },
        {
            "id": "draft-remedy",
            "role": "learner named remediation proposer",
            "identity_ref": "identity.remediation_agent",
            "capability_ref": "propose_refund",
            "action": "propose_refund",
        },
        {
            "id": "route-review",
            "role": "learner named review router",
            "identity_ref": "identity.compliance_officer",
            "capability_ref": "request_human_approval",
            "action": "request_approval",
        },
        {
            "id": "customer-update",
            "role": "learner named customer communicator",
            "identity_ref": notification_identity,
            "capability_ref": "notify_customer_external",
            "action": "notify_customer",
        },
        {
            "id": "case-close",
            "role": "learner named case owner",
            "identity_ref": "identity.compliance_officer",
            "capability_ref": "close_case",
            "action": "close_case",
        },
    ]


def test_template_describes_an_authored_executable_capstone() -> None:
    definition = capstone_template()

    assert isinstance(definition, CapstoneDefinition)
    assert definition.id == "24"
    assert definition.assessment_id == "assessment.24"
    assert definition.frameworks == ("framework-neutral", "crewai", "langgraph")
    assert set(definition.failure_injections) == {
        "prompt-injection",
        "expired-approval",
        "artifact-tamper",
        "unauthorized-delegation",
        "replay",
        "bypass",
    }
    assert "Author" in definition.summary
    assert any("claim" in requirement.lower() for requirement in definition.requirements)


def test_default_capstone_passes_the_full_definition_of_done() -> None:
    run = run_capstone()

    assert isinstance(run, StructuredLabRun)
    assert run.module_id == "24"
    assert run.completion_eligible is True
    assert all(run.results["completion_checks"].values())
    controlled = _variant(run, "controlled")
    reference = _variant(run, "reference")
    assert controlled["notification_attempts"] == controlled["notification_completions"] == 0
    assert reference["notification_attempts"] == reference["notification_completions"] == 1
    assert controlled["evidence_validation"]["status"] == "pass"
    assert reference["evidence_validation"]["status"] == "pass"
    assert run.results["design_review"]["valid"] is True
    assert run.results["assurance_review"]["defensible"] is True


def test_structured_learner_design_drives_roles_timeline_and_run_identity() -> None:
    inputs = {
        "roles": _roles(),
        "trust_zones": {
            "source_zone": "zone.remediation_internal",
            "target_zone": "zone.customer_channel",
        },
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
                "On the named synchronous customer-update path, real Nornyx decisions "
                "precede the inert notification callable."
            ),
            "residual_risk": (
                "Direct bypass, actor authentication, credentials, and network egress remain "
                "outside this cooperative surface."
            ),
            "falsification_condition": (
                "Falsify the claim if the customer-update callable completes without those "
                "preceding decisions."
            ),
        },
    }

    authored = run_capstone(inputs)
    starter = run_capstone()

    assert authored.run_id != starter.run_id
    assert authored.results["configuration"]["roles"][0]["role"] == ("learner named triage owner")
    roles = {event["role"] for event in _variant(authored, "reference")["timeline"]}
    assert "learner named investigator" in roles
    assert "learner named customer communicator" in roles
    assert authored.results["claim_register"]["learner_claim"].startswith(
        "On the named synchronous"
    )
    assert authored.completion_eligible is True


def test_capability_allocation_changes_real_decisions_business_outcome_and_eligibility() -> None:
    valid = run_capstone({"roles": _roles()})
    invalid = run_capstone({"roles": _roles(notification_identity="identity.case_analyst")})

    assert _variant(valid, "reference")["notification_completions"] == 1
    assert _variant(invalid, "reference")["notification_completions"] == 0
    invalid_allocation = next(
        item
        for item in invalid.results["design_review"]["capability_allocations"]
        if item["step_id"] == "customer-update"
    )
    assert invalid_allocation["decision_code"] == "CAPABILITY_DENIED"
    assert invalid_allocation["valid"] is False
    assert invalid.results["completion_checks"]["design_valid"] is False
    assert invalid.completion_eligible is False


def test_zone_and_coordination_choices_change_execution_instead_of_only_presentation() -> None:
    wrong_zone = run_capstone(
        {
            "roles": _roles(),
            "trust_zones": {
                "source_zone": "zone.customer_channel",
                "target_zone": "zone.remediation_internal",
            },
        }
    )
    wrong_delegation = run_capstone(
        {
            "roles": _roles(),
            "coordination": {
                "delegation_id": "delegation.not_declared",
                "handoff_id": "handoff.compliance_closure",
                "require_delegation": True,
                "require_handoff": True,
            },
        }
    )

    assert _variant(wrong_zone, "reference")["notification_completions"] == 0
    crossing = next(
        row
        for row in _variant(wrong_zone, "reference")["decisions"]
        if row["stage"] == "customer crossing"
    )
    assert crossing["effect"] == "deny"
    assert wrong_zone.completion_eligible is False

    proposal = next(
        item
        for item in _variant(wrong_delegation, "reference")["runtime_outcomes"]
        if item["action"] == "propose_refund"
    )
    assert proposal["entered_business_callable"] is False
    assert "declared delegation" in proposal["blockers"]
    assert _variant(wrong_delegation, "reference")["notification_completions"] == 0
    assert wrong_delegation.results["completion_checks"]["design_valid"] is False


def test_capstone_is_deterministic_for_the_same_authored_configuration() -> None:
    config = CapstoneConfig(
        framework="framework-neutral",
        failure_injection="expired-approval",
        scaffolding="reduced",
    )

    first = run_capstone(config)
    second = run_capstone(config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


@pytest.mark.parametrize(
    "failure",
    [
        "prompt-injection",
        "expired-approval",
        "artifact-tamper",
        "unauthorized-delegation",
        "replay",
        "bypass",
    ],
)
def test_every_controlled_failure_changes_execution_or_evidence_and_is_repo_safe(
    failure: str,
) -> None:
    contract = shared_contract("ledger")
    files = (contract / "network.nyx", contract / "nornyx.agentic_network.lock")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

    run = run_capstone(
        {
            "framework": "framework-neutral",
            "failure_injection": failure,
            "scaffolding": "guided",
        }
    )

    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    injection = run.results["failure_injection"]
    assert before == after
    assert injection["kind"] == failure
    assert injection["repository_mutated"] is False
    assert injection["handled"] is True
    assert injection.get("execution_changed") is True or injection.get("evidence_changed") is True
    assert _variant(run, "reference")["notification_completions"] == 1
    assert run.completion_eligible is True


def test_prompt_injection_adds_a_real_executable_step_and_real_refusal_evidence() -> None:
    run = run_capstone({"failure_injection": "prompt-injection"})
    controlled = _variant(run, "controlled")
    injected = next(item for item in controlled["runtime_outcomes"] if item["injected"])

    assert injected["step_id"] == "injected-notification"
    assert injected["entered_business_callable"] is False
    assert injected["crossing_effect"] in {"deny", "approval_required"}
    assert controlled["evidence_validation"]["status"] == "pass"
    assert controlled["evidence_validation"]["event_count"] > 0


def test_expired_approval_uses_a_real_specific_refusal() -> None:
    run = run_capstone({"failure_injection": "expired-approval"})
    controlled = _variant(run, "controlled")

    assert any(decision["code"] == "APPROVAL_STALE" for decision in controlled["decisions"])
    assert controlled["notification_completions"] == 0


def test_artifact_tamper_blocks_execution_without_forging_a_nornyx_decision() -> None:
    run = run_capstone({"failure_injection": "artifact-tamper"})
    controlled = _variant(run, "controlled")
    preflight = controlled["preflight"]

    assert preflight["code"] == "ACADEMY_ARTIFACT_DIGEST_MISMATCH"
    assert preflight["expected_digest"] != preflight["observed_digest"]
    assert preflight["repository_mutated"] is False
    integrity_row = next(
        row for row in controlled["decisions"] if row["stage"] == "artifact integrity preflight"
    )
    assert integrity_row["nornyx_decision"] is False
    assert all(not item["entered_business_callable"] for item in controlled["runtime_outcomes"])


def test_replay_changes_an_evidence_copy_and_is_detected_without_corrupting_original() -> None:
    run = run_capstone({"failure_injection": "replay"})
    injection = run.results["failure_injection"]

    assert injection["evidence_copy_validation"] == "fail"
    assert injection["duplicate_identities"]
    assert injection["replayed_event_count"] == injection["original_event_count"] + 1
    assert _variant(run, "controlled")["evidence_validation"]["status"] == "pass"


def test_bypass_negative_control_constrains_the_assurance_claim() -> None:
    run = run_capstone({"failure_injection": "bypass"})
    injection = run.results["failure_injection"]

    assert injection["bypass_notification_completions"] == 1
    assert injection["nornyx_decisions_on_bypass"] == 0
    assert "direct business-call bypass" in run.results["claim_register"]["uncovered"]
    assert run.results["assurance_review"]["defensible"] is True


def test_broad_assurance_claim_fails_completion_even_when_execution_passes() -> None:
    run = run_capstone(
        {
            "assurance": {
                "claim": "The whole application is governed and cannot be bypassed by any agent.",
                "residual_risk": (
                    "Direct bypass and approver authentication remain outside the tested boundary."
                ),
                "falsification_condition": (
                    "Falsify this statement if any notification happens without a decision."
                ),
            }
        }
    )

    assert _variant(run, "reference")["notification_completions"] == 1
    assert run.results["assurance_review"]["wording_checks"]["claim_avoids_absolutes"] is False
    assert run.results["completion_checks"]["assurance_review_defensible"] is False
    assert run.results["claim_register"]["accepted"] is False
    assert run.completion_eligible is False


def test_crewai_executes_the_real_pinned_kickoff_and_governed_tool_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crewai = pytest.importorskip("crewai")
    pytest.importorskip("nornyx_agentic_adapters.crewai_adapter")
    calls = 0
    original = crewai.Crew.kickoff

    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(crewai.Crew, "kickoff", counted)
    run = run_capstone({"framework": "crewai"})

    assert calls == 2
    for variant in run.results["variants"]:
        runtime = variant["framework_runtime"]
        assert runtime["actual_framework_execution"] is True
        assert runtime["completed"] is True
        assert runtime["versions"] == {"framework": "1.15.4", "adapter": "0.3.0"}
        assert "Crew.kickoff" in runtime["governed_surface"]
        assert variant["evidence_validation"]["status"] == "pass"
    assert "async tool invocation" in run.safety_boundary
    assert run.completion_eligible is True


def test_langgraph_executes_real_pinned_stategraphs_and_governed_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = pytest.importorskip("langgraph.graph")
    pytest.importorskip("nornyx_agentic_adapters.langgraph")
    calls = 0
    original = graph.StateGraph.compile

    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(graph.StateGraph, "compile", counted)
    run = run_capstone({"framework": "langgraph"})

    assert calls == 2
    for variant in run.results["variants"]:
        runtime = variant["framework_runtime"]
        assert runtime["actual_framework_execution"] is True
        assert runtime["completed"] is True
        assert runtime["versions"] == {"framework": "1.2.2", "adapter": "0.3.0"}
        assert "StateGraph.invoke" in runtime["governed_surface"]
        assert variant["evidence_validation"]["status"] == "pass"
        assert len(variant["evidence_streams"]) == 2
    assert "unwrapped/async nodes" in run.safety_boundary
    assert run.completion_eligible is True


@pytest.mark.parametrize(
    "inputs",
    [
        {"framework": "autogen"},
        {"failure_injection": "real-network-call"},
        {"scaffolding": "answers-shown"},
        {"unknown": True},
        {"roles": []},
        {"roles": [{"id": "only"}]},
        {"trust_zones": {"extra": True}},
        {"coordination": {"require_handoff": "yes"}},
        {"policy": {"approval_mode": "automatic"}},
        {"assurance": {"claim": "too short"}},
        [],
    ],
)
def test_invalid_capstone_configuration_fails_closed(inputs: object) -> None:
    with pytest.raises(CapstoneInputError):
        run_capstone(inputs)  # type: ignore[arg-type]

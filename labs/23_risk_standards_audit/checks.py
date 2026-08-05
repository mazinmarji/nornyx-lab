"""Concept checks for Lab 23 — threat branches, attempted rather than asserted."""

from __future__ import annotations

import json

from nornyx.agentic import CapabilityRequest, EvaluationContext, EvidenceRecorder

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, lock_check, nornyx, shared_contract

ATLAS = shared_contract("atlas")
LEDGER = shared_contract("ledger")
ID = "identity.research_assistant"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def _probe(mutation) -> list[str]:
    """Write a mutated contract beside the real one, check it, clean up."""
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    probe = ATLAS / "threat_probe.nyx"
    probe.write_text(mutation(original), encoding="utf-8")
    try:
        result = nornyx("check", "threat_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        assert not result.ok, "this threat branch should be blocked"
        return result.codes()
    finally:
        probe.unlink(missing_ok=True)


# ------------------------------------------------- tree 1: subvert the contract
def test_branch_widen_a_superior_control_is_blocked():
    codes = _probe(
        lambda t: t.replace(
            "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]",
            "denied_actor_types: [connector]",
        )
    )
    assert "APPROVAL_CORE_DENIAL_MISSING" in codes, codes


def test_branch_add_an_unrecognised_block_is_detected_but_not_blocked():
    """An honest branch: reported with a stable code, and the check still passes.

    Recording this row as "blocked" would be exactly the overclaim Lab 12 is
    about. Gating on the code is the pipeline's job, not the checker's.
    """
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    probe = ATLAS / "threat_probe.nyx"
    probe.write_text(original + "\nbackdoor:\n  - name: skip_everything\n", encoding="utf-8")
    try:
        result = nornyx("check", "threat_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        unknown = [d for d in result.diagnostics() if d.get("code") == "UNKNOWN_TOP_LEVEL_BLOCK"]
        assert unknown, "the block must at least be named"
        assert unknown[0]["level"] == "warning"
        assert result.ok, "detection, not prevention"
    finally:
        probe.unlink(missing_ok=True)


def test_branch_swap_in_another_contracts_lock_is_blocked():
    result = lock_check(
        ATLAS / "network.nyx",
        LEDGER / "nornyx.agentic_network.lock",
        ATLAS / "control_artifacts",
        cwd=ATLAS,
    )
    assert not result.ok


def test_branch_use_an_unheld_capability_is_blocked():
    decision = authorizer_for(ATLAS).evaluate(
        CapabilityRequest(ID, "publish_external"), context=_ctx()
    )
    assert not decision.allowed
    assert decision.code.value == "CAPABILITY_DENIED"


# --------------------------------------------------- tree 2: subvert the record
def test_branch_edit_an_evidence_file_is_blocked():
    victim = ATLAS / "governance_evidence" / "approval_record.json"
    original = victim.read_bytes()
    try:
        victim.write_bytes(original.replace(b'"status":"pass"', b'"status":"fail"'))
        result = nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        assert not result.ok, "a changed evidence artifact must break its digest"
    finally:
        victim.write_bytes(original)
    assert nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS).ok


def test_branch_never_writing_the_event_is_NOT_mitigated():
    """The honest one. This branch has no mechanism, and the test says so.

    If a future version of this stack gains independent attestation, this test
    should be rewritten to assert detection — and that rewrite is the moment the
    Tier 2 ceiling lifts.
    """
    from nornyx_lab import northstar
    from nornyx_lab.ledger import Ledger

    silent = Ledger("dishonest producer")
    # The effect happens somewhere in the process; this producer records nothing.
    _ = f"refund:acct-88213:{5000.0:.2f}"

    assert len(silent) == 0
    assert silent.to_dict()["entries"] == Ledger("never ran").to_dict()["entries"], (
        "a silent producer is indistinguishable from a prevented action at Tier 2"
    )

    honest = Ledger("honest")
    northstar.issue_refund(honest, 5000.0)
    assert honest.completions("issue_refund") == 1


# -------------------------------------------------------------- audit package
def test_the_audit_package_leads_with_a_claim_register(tmp_path):
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.audit")
    recorder.record_decision(
        az.evaluate(CapabilityRequest(ID, "publish_external"), context=ctx),
        mission_id="mission.audit-sample",
    )
    report = recorder.validate()

    register = {
        "subject_revision": LAB_SUBJECT_REVISION,
        "claims": [
            {
                "id": "CLAIM-001",
                "tier": 2,
                "surface": "crewai tool_invocation (sync)",
                "uncovered": ["direct invocation", "async tool path"],
                "falsified_by": "one completed publish with no preceding decision",
            }
        ],
    }
    (tmp_path / "claim_register.json").write_text(json.dumps(register, indent=2), encoding="utf-8")

    claim = register["claims"][0]
    assert claim["uncovered"], "a claim with no uncovered list is not finished"
    assert claim["falsified_by"], "a claim you cannot falsify is not a claim"
    assert claim["tier"] == 2
    assert report["status"] == "pass"
    assert report["subject_revision"] == LAB_SUBJECT_REVISION


def test_the_validator_report_carries_its_own_caveats():
    """The 'caveats' field of a mapping row is not something you invent."""
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.audit")
    recorder.record_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx), mission_id="m"
    )
    assert recorder.validate().get("limitations")

"""Concept checks for Lab 18 — the five-test rule against the CrewAI surface."""

from __future__ import annotations

import pytest
from nornyx.agentic import EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger
from nornyx_lab.optional import skip_unless

MISSION = "mission.remediation"


@pytest.fixture
def kit():
    adapter = skip_unless("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    from nornyx_agentic_adapters import SurfaceBinding
    from nornyx_agentic_adapters.errors import AdapterDenied

    az = authorizer_for(shared_contract("ledger"))
    ctx = EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.crewai")
    ledger = Ledger("governed")

    def build(identity: str, capability: str, action_name: str):
        return adapter.make_governed_tool(
            name=f"tool_{capability}",
            description=f"Business tool for {capability}.",
            binding=SurfaceBinding(
                surface="tool_invocation", identity_ref=identity, capability_ref=capability
            ),
            authorizer=az,
            context=ctx,
            recorder=recorder,
            mission_id=MISSION,
            action=lambda **kw: northstar.perform(ledger, action_name, **kw),
        )

    return {
        "adapter": adapter,
        "build": build,
        "ledger": ledger,
        "recorder": recorder,
        "AdapterDenied": AdapterDenied,
    }


def test_1_allow_the_authorized_tool_runs(kit):
    kit["build"]("identity.case_analyst", "read_customer_case", "read_case").run()

    assert kit["ledger"].attempts("read_case") == 1
    assert kit["ledger"].completions("read_case") == 1


def test_2_deny_the_business_callable_is_never_entered(kit):
    tool = kit["build"]("identity.case_analyst", "issue_refund", "issue_refund")
    with pytest.raises(kit["AdapterDenied"]):
        tool.run()

    assert kit["ledger"].attempts("issue_refund") == 0, "prevented, not merely failed"
    assert kit["ledger"].completions("issue_refund") == 0


def test_3_failure_a_broken_authorizer_does_not_let_the_action_through(kit):
    from nornyx_agentic_adapters import SurfaceBinding

    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("authorizer unavailable")

    ledger = Ledger("failure")
    with pytest.raises((RuntimeError, AttributeError, TypeError, kit["AdapterDenied"])):
        kit["adapter"].make_governed_tool(
            name="broken",
            description="x",
            binding=SurfaceBinding(
                surface="tool_invocation",
                identity_ref="identity.case_analyst",
                capability_ref="issue_refund",
            ),
            authorizer=Broken(),
            context=EvaluationContext(
                decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
            ),
            recorder=kit["recorder"],
            mission_id=MISSION,
            action=lambda **kw: northstar.issue_refund(ledger, 5000.0),
        ).run()

    assert ledger.attempts("issue_refund") == 0


def test_4_bypass_the_underlying_callable_is_still_reachable(kit):
    """Declared, not fixed. Tier 2 cannot close this."""
    tool = kit["build"]("identity.case_analyst", "issue_refund", "issue_refund")
    with pytest.raises(kit["AdapterDenied"]):
        tool.run()

    northstar.issue_refund(kit["ledger"], 5000.0)  # straight past the wrapper
    assert kit["ledger"].completions("issue_refund") == 1


def test_5_evidence_the_decision_precedes_execution_and_validates(kit):
    kit["build"]("identity.case_analyst", "read_customer_case", "read_case").run()
    report = kit["recorder"].validate()

    assert report["status"] == "pass"
    counts = report["counts_by_type"]
    assert counts.get("capability_requested", 0) >= 1
    assert counts.get("tool_invoked", 0) >= 1, "the post-action observation is recorded"


def test_a_denial_still_produces_evidence(kit):
    tool = kit["build"]("identity.case_analyst", "issue_refund", "issue_refund")
    with pytest.raises(kit["AdapterDenied"]):
        tool.run()

    report = kit["recorder"].validate()
    assert report["status"] == "pass"
    assert report["counts_by_type"].get("capability_denied", 0) >= 1


def test_a_binding_to_an_undeclared_capability_is_a_configuration_error(kit):
    """Different from a denial, and it must be distinguishable."""
    tool = kit["build"]("identity.case_analyst", "no_such_capability", "read_case")
    with pytest.raises((kit["AdapterDenied"], ValueError, RuntimeError)) as exc:
        tool.run()

    assert "no_such_capability" in str(exc.value) or "UNKNOWN" in str(exc.value).upper()
    assert kit["ledger"].attempts("read_case") == 0


def test_the_adapter_pins_its_framework_version(kit):
    """An exact pin that fails closed at import is a governance property."""
    metadata = kit["adapter"].METADATA
    assert "==" in metadata.framework_version_range
    assert metadata.spi_version
    assert metadata.adapter_version


def test_the_async_surface_is_declared_unsupported(kit):
    from nornyx_agentic_adapters import SurfaceStatus

    entries = {e.surface: e for e in kit["adapter"].COVERAGE_INVENTORY.entries}
    assert entries["tool_invocation"].status is SurfaceStatus.WRAPPED
    assert entries["async_tool_invocation"].status is SurfaceStatus.UNSUPPORTED

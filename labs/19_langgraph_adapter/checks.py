"""Concept checks for Lab 19."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import pytest
from nornyx.agentic import EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger
from nornyx_lab.optional import skip_unless

MISSION = "mission.graph"


class GraphState(TypedDict):
    log: Annotated[list, operator.add]


@pytest.fixture
def kit():
    adapter = skip_unless("nornyx_agentic_adapters.langgraph", extra="langgraph")
    skip_unless("langgraph.graph", extra="langgraph")
    from nornyx_agentic_adapters import SurfaceBinding
    from nornyx_agentic_adapters.errors import AdapterDenied

    az = authorizer_for(shared_contract("ledger"))
    ctx = EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)
    recorder = EvidenceRecorder.for_occurrences(az, ctx, producer_id="nornyx-lab.langgraph")
    ledger = Ledger("graph")

    def governed(identity: str, capability: str, action):
        return adapter.make_governed_node(
            binding=SurfaceBinding(
                surface="node_invocation", identity_ref=identity, capability_ref=capability
            ),
            authorizer=az,
            context=ctx,
            recorder=recorder,
            mission_id=MISSION,
            action=action,
        )

    return {
        "adapter": adapter,
        "governed": governed,
        "ledger": ledger,
        "recorder": recorder,
        "AdapterDenied": AdapterDenied,
    }


def _build_graph(kit):
    from langgraph.graph import END, START, StateGraph

    ledger = kit["ledger"]
    graph = StateGraph(GraphState)
    graph.add_node(
        "read",
        kit["governed"](
            "identity.intake_agent",
            "read_customer_case",
            lambda state: {"log": [northstar.read_case(ledger, "CASE-1041")["case_id"]]},
        ),
    )
    graph.add_node(
        "refund",
        kit["governed"](
            "identity.intake_agent",
            "issue_refund",
            lambda state: {"log": [northstar.issue_refund(ledger, 5000.0)]},
        ),
    )
    graph.add_edge(START, "read")
    graph.add_edge("read", "refund")
    graph.add_edge("refund", END)
    return graph.compile()


def test_the_graph_halts_at_the_unauthorized_node(kit):
    app = _build_graph(kit)
    with pytest.raises(kit["AdapterDenied"]):
        app.invoke({"log": []})

    assert kit["ledger"].completions("read_case") == 1, "the authorized node ran"
    assert kit["ledger"].attempts("issue_refund") == 0, "the unauthorized one was not entered"
    assert kit["ledger"].completions("issue_refund") == 0


def test_evidence_from_a_real_graph_run_validates(kit):
    app = _build_graph(kit)
    with pytest.raises(kit["AdapterDenied"]):
        app.invoke({"log": []})

    report = kit["recorder"].validate()
    assert report["status"] == "pass"
    assert report["diagnostics"] == []
    assert report["counts_by_type"].get("capability_denied", 0) >= 1


def test_occurrence_identity_is_present_and_framework_derived(kit):
    app = _build_graph(kit)
    with pytest.raises(kit["AdapterDenied"]):
        app.invoke({"log": []})

    events = [e for e in kit["recorder"].stream()["events"] if "occurrence" in e]
    assert events, "explicit occurrence mode must stamp every event"

    for event in events:
        occurrence = event["occurrence"]
        assert occurrence["operation_id"] == "node_invocation"
        assert occurrence["attempt"] >= 1
        # The id comes from LangGraph's per-task metadata, so it is a runtime
        # value: assert its shape, never its literal content.
        assert isinstance(occurrence["occurrence_id"], str)
        assert len(occurrence["occurrence_id"]) > 8


def test_two_nodes_get_distinct_occurrences(kit):
    """Separate scheduled executions are separate occurrences, not attempts."""
    app = _build_graph(kit)
    with pytest.raises(kit["AdapterDenied"]):
        app.invoke({"log": []})

    ids = {
        e["occurrence"]["occurrence_id"]
        for e in kit["recorder"].stream()["events"]
        if "occurrence" in e
    }
    assert len(ids) >= 2


def test_the_stream_is_in_explicit_occurrence_mode(kit):
    app = _build_graph(kit)
    with pytest.raises(kit["AdapterDenied"]):
        app.invoke({"log": []})

    assert kit["recorder"].stream()["occurrence_mode"] == "explicit"


def test_the_langgraph_adapter_publishes_gaps_too(kit):
    from nornyx_agentic_adapters import SurfaceStatus

    entries = kit["adapter"].COVERAGE_INVENTORY.entries
    statuses = {e.status for e in entries}
    assert SurfaceStatus.WRAPPED in statuses
    assert SurfaceStatus.UNSUPPORTED in statuses
    for entry in entries:
        assert entry.reason


def test_both_adapters_share_one_decision_engine(kit):
    """The point of the boundary: two frameworks, one interpretation."""
    crewai = skip_unless("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    assert crewai.SPI_VERSION == kit["adapter"].SPI_VERSION
    assert crewai.METADATA.framework_name != kit["adapter"].METADATA.framework_name

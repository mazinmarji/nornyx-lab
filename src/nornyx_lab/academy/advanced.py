"""Executable browser-native replacements for legacy Labs 19, 22, and 23.

These modules return typed cards, tables, counters, and evidence summaries.  They
never expose a terminal transcript and never write to the repository.  Every
business effect is an in-memory Northstar fixture; every Nornyx decision comes
from a lock-verified authorizer loaded through the supported public SPI.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import tempfile
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

import yaml
from nornyx.agentic import (
    ApprovalAssertion,
    ApprovalRequest,
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    EvidenceRecorder,
    HandoffRequest,
    ZoneCrossingRequest,
    build_agentic_network_lock,
    check_document,
    compose_document_governance,
    evaluate_document_governance,
    load_authorizer,
    load_nyx,
    registry_for_contract,
    render_agentic_network_artifacts,
    write_agentic_network_lock,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger

from .schemas import (
    BlockKind,
    ContentBlock,
    EvidenceFinding,
    EvidenceStatus,
    RunStatus,
    StructuredLabRun,
)

ADVANCED_MODULE_IDS = ("19", "22", "23")
_LANGGRAPH_VERSION = "1.2.2"
_LANGGRAPH_ADAPTER_VERSION = "0.3.0"


class AdvancedInputError(ValueError):
    """Raised when a browser submits unsupported advanced-module input."""


class _LoopState(TypedDict):
    count: int


class _ParallelState(TypedDict, total=False):
    left: int
    right: int


class _ValueState(TypedDict, total=False):
    value: int
    answer: str


def _inputs(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdvancedInputError("advanced-module inputs must be a JSON object")
    return dict(value)


def _only(values: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise AdvancedInputError(f"unsupported input field(s): {', '.join(unknown)}")


def _boolean(value: Any, *, name: str, default: bool) -> bool:
    selected = default if value is None else value
    if not isinstance(selected, bool):
        raise AdvancedInputError(f"{name} must be true or false")
    return selected


def _choice(value: Any, *, name: str, default: str, choices: set[str]) -> str:
    selected = default if value is None else value
    if not isinstance(selected, str) or selected not in choices:
        shown = ", ".join(sorted(choices))
        raise AdvancedInputError(f"{name} must be one of: {shown}")
    return selected


def _run_id(module_id: str, values: Mapping[str, Any]) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return f"advanced-{module_id}-{hashlib.sha256(encoded).hexdigest()[:12]}"


def _block(
    block_id: str,
    kind: BlockKind,
    *,
    title: str | None = None,
    body: str = "",
    rows: tuple[dict[str, Any], ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        kind=kind,
        title=title,
        body=body,
        rows=rows,
        metadata=dict(metadata or {}),
    )


@lru_cache(maxsize=2)
def _authorizer(contract_name: str) -> Any:
    """Cache the immutable authorizer; every run gets a fresh evidence recorder."""

    return authorizer_for(shared_contract(contract_name))


def _evaluation_context() -> EvaluationContext:
    return EvaluationContext(
        decision_at=LAB_AS_OF,
        observed_subject_revision=LAB_SUBJECT_REVISION,
    )


def _evidence_summary(recorder: EvidenceRecorder) -> dict[str, Any]:
    report = recorder.validate()
    counts = report.get("counts_by_type", {})
    return {
        "status": str(report.get("status", "unknown")),
        "event_count": int(report.get("event_count", 0)),
        "counts_by_type": {
            str(key): int(value) for key, value in sorted(counts.items()) if isinstance(value, int)
        }
        if isinstance(counts, Mapping)
        else {},
        "contract_digest_bound": str(report.get("contract_digest", "")).startswith("sha256:"),
        "network_lock_digest_bound": str(report.get("network_lock_digest", "")).startswith(
            "sha256:"
        ),
        "subject_revision": str(report.get("subject_revision", "")),
        "limitations": tuple(str(item) for item in report.get("limitations", ())),
    }


def _decision(decision: Any) -> dict[str, Any]:
    return {
        "effect": decision.effect.value,
        "code": decision.code.value,
        "allowed": decision.allowed,
        "basis": tuple(
            {"kind": item.kind, "ref": item.ref, "detail": item.detail} for item in decision.basis
        ),
    }


def _unavailable_19(reason: str) -> StructuredLabRun:
    return StructuredLabRun(
        run_id=_run_id("19", {"mode": "comprehensive", "dependency": "unavailable"}),
        module_id="19",
        legacy_lab_id="19",
        title="LangGraph Runtime Semantics and Coverage",
        status=RunStatus.UNAVAILABLE,
        blocks=(
            _block(
                "lab-19-unavailable",
                BlockKind.BOUNDARY,
                title="Real framework execution unavailable",
                body=reason,
            ),
        ),
        results={
            "framework": {
                "name": "langgraph",
                "required_version": _LANGGRAPH_VERSION,
                "adapter_required_version": _LANGGRAPH_ADAPTER_VERSION,
                "actual_execution": False,
                "fallback_used": False,
            }
        },
        diagnostics=(
            EvidenceFinding(
                status=EvidenceStatus.MISSING,
                code="LANGGRAPH_RUNTIME_UNAVAILABLE",
                message=reason,
            ),
        ),
        executable_checks=(),
        completion_eligible=False,
        unavailable_reason=reason,
        safety_boundary=(
            "No substitute graph, network call, subprocess, repository write, or business effect "
            "was attempted."
        ),
    )


def _failed_19(kind: str) -> StructuredLabRun:
    reason = f"The real LangGraph exercise failed closed during {kind}."
    return StructuredLabRun(
        run_id=_run_id("19", {"mode": "comprehensive", "failure": kind}),
        module_id="19",
        legacy_lab_id="19",
        title="LangGraph Runtime Semantics and Coverage",
        status=RunStatus.FAILED,
        blocks=(
            _block(
                "lab-19-failed",
                BlockKind.DIAGNOSTICS,
                title="Executable check failed",
                body=reason,
                rows=({"code": "LANGGRAPH_EXECUTION_FAILED", "phase": kind},),
            ),
        ),
        results={"failed_phase": kind, "fallback_used": False},
        diagnostics=(
            EvidenceFinding(
                status=EvidenceStatus.FAIL,
                code="LANGGRAPH_EXECUTION_FAILED",
                message=reason,
            ),
        ),
        executable_checks=(),
        completion_eligible=False,
        safety_boundary=(
            "Execution remained in memory. No network, subprocess, repository mutation, or "
            "external business effect was reachable."
        ),
    )


def _load_langgraph() -> tuple[dict[str, Any] | None, str | None]:
    """Load optional framework pieces without substituting a teaching fixture."""

    try:
        graph = importlib.import_module("langgraph.graph")
        types = importlib.import_module("langgraph.types")
        memory = importlib.import_module("langgraph.checkpoint.memory")
        adapter = importlib.import_module("nornyx_agentic_adapters.langgraph")
        binding = importlib.import_module("nornyx_agentic_adapters.binding")
        errors = importlib.import_module("nornyx_agentic_adapters.errors")
        installed = importlib.metadata.version("langgraph")
        adapter_installed = importlib.metadata.version("nornyx-agentic-adapters")
    except (ImportError, ModuleNotFoundError, importlib.metadata.PackageNotFoundError):
        return None, (
            "LangGraph 1.2.2 and nornyx-agentic-adapters 0.3.0 are required for this "
            "module. The dependency is absent, so the academy reports UNAVAILABLE instead of "
            "showing modeled output."
        )
    except Exception as exc:  # adapter import enforces its exact compatibility pin
        if type(exc).__name__ == "AdapterConfigurationError":
            return None, (
                "The installed LangGraph runtime does not satisfy the adapter's exact "
                "compatibility guard. The academy reports UNAVAILABLE without a fallback."
            )
        raise
    if installed != _LANGGRAPH_VERSION or adapter_installed != _LANGGRAPH_ADAPTER_VERSION:
        return None, (
            f"This exercise requires LangGraph {_LANGGRAPH_VERSION} and the Nornyx adapter "
            f"{_LANGGRAPH_ADAPTER_VERSION}; the exact compatibility check did not match."
        )
    return (
        {
            "graph": graph,
            "types": types,
            "memory": memory,
            "adapter": adapter,
            "binding": binding,
            "errors": errors,
            "version": installed,
            "adapter_version": adapter_installed,
        },
        None,
    )


def _governed_node(
    dependencies: Mapping[str, Any],
    *,
    authorizer: Any,
    recorder: EvidenceRecorder,
    mission_id: str,
    action: Any,
    identity_ref: str = "identity.intake_agent",
    capability_ref: str = "read_customer_case",
) -> Any:
    binding = dependencies["binding"].SurfaceBinding(
        surface="sync_node_invocation",
        identity_ref=identity_ref,
        capability_ref=capability_ref,
    )
    return dependencies["adapter"].make_governed_node(
        binding=binding,
        authorizer=authorizer,
        context=_evaluation_context(),
        recorder=recorder,
        mission_id=mission_id,
        action=action,
    )


def _occurrence_summary(recorder: EvidenceRecorder) -> dict[str, Any]:
    stream = recorder.stream()
    events = tuple(item for item in stream.get("events", ()) if isinstance(item, Mapping))
    occurrences: set[tuple[str, int]] = set()
    event_types: Counter[str] = Counter()
    for event in events:
        event_types[str(event.get("event_type", "unknown"))] += 1
        occurrence = event.get("occurrence")
        if isinstance(occurrence, Mapping):
            occurrence_id = occurrence.get("occurrence_id")
            attempt = occurrence.get("attempt")
            if isinstance(occurrence_id, str) and isinstance(attempt, int):
                occurrences.add((occurrence_id, attempt))
    ids = {occurrence_id for occurrence_id, _attempt in occurrences}
    attempts = sorted({attempt for _occurrence_id, attempt in occurrences})
    return {
        "occurrence_mode": stream.get("occurrence_mode"),
        "metadata_source": "LangGraph Runtime.execution_info.task_id and node_attempt",
        "raw_runtime_ids_exposed": False,
        "distinct_occurrences": len(ids),
        "attempts": tuple(attempts),
        "event_types": dict(sorted(event_types.items())),
        "evidence": _evidence_summary(recorder),
    }


def _compile_single(
    dependencies: Mapping[str, Any],
    node: Any,
    *,
    retry_policy: Any = None,
    checkpointer: Any = None,
) -> Any:
    graph = dependencies["graph"]
    builder = graph.StateGraph(_ValueState)
    builder.add_node("work", node, retry_policy=retry_policy)
    builder.add_edge(graph.START, "work")
    builder.add_edge("work", graph.END)
    return builder.compile(checkpointer=checkpointer)


def _langgraph_patterns(dependencies: Mapping[str, Any]) -> dict[str, Any]:
    authorizer = _authorizer("ledger")

    retry_recorder = EvidenceRecorder.for_occurrences(
        authorizer, _evaluation_context(), producer_id="nornyx-lab.academy.langgraph.retry"
    )
    retry_calls = 0

    def flaky(_state: Any) -> dict[str, int]:
        nonlocal retry_calls
        retry_calls += 1
        if retry_calls < 3:
            raise ValueError("deterministic retry fixture")
        return {"value": retry_calls}

    retry_node = _governed_node(
        dependencies,
        authorizer=authorizer,
        recorder=retry_recorder,
        mission_id="mission.academy.lab19.retry",
        action=flaky,
    )
    retry_policy = dependencies["types"].RetryPolicy(
        max_attempts=3,
        retry_on=ValueError,
        initial_interval=0,
    )
    retry_output = _compile_single(dependencies, retry_node, retry_policy=retry_policy).invoke({})
    retry = {
        "actual_framework_execution": True,
        "calls": retry_calls,
        "output": retry_output.get("value"),
        **_occurrence_summary(retry_recorder),
    }
    retry["passed"] = (
        retry["calls"] == 3
        and retry["output"] == 3
        and retry["distinct_occurrences"] == 1
        and retry["attempts"] == (1, 2, 3)
        and retry["event_types"].get("runtime_failed") == 2
        and retry["event_types"].get("agent_invoked") == 1
        and retry["evidence"]["status"] == "pass"
    )

    loop_recorder = EvidenceRecorder.for_occurrences(
        authorizer, _evaluation_context(), producer_id="nornyx-lab.academy.langgraph.loop"
    )
    loop_calls = 0

    def visit(state: _LoopState) -> dict[str, int]:
        nonlocal loop_calls
        loop_calls += 1
        return {"count": state["count"] + 1}

    loop_node = _governed_node(
        dependencies,
        authorizer=authorizer,
        recorder=loop_recorder,
        mission_id="mission.academy.lab19.loop",
        action=visit,
    )
    graph = dependencies["graph"]
    loop_builder = graph.StateGraph(_LoopState)
    loop_builder.add_node("loop", loop_node)
    loop_builder.add_edge(graph.START, "loop")
    loop_builder.add_conditional_edges(
        "loop", lambda state: "loop" if state["count"] < 2 else graph.END
    )
    loop_output = loop_builder.compile().invoke({"count": 0})
    loop = {
        "actual_framework_execution": True,
        "calls": loop_calls,
        "output": loop_output.get("count"),
        **_occurrence_summary(loop_recorder),
    }
    loop["passed"] = (
        loop["calls"] == 2
        and loop["output"] == 2
        and loop["distinct_occurrences"] == 2
        and loop["attempts"] == (1,)
        and loop["evidence"]["status"] == "pass"
    )

    parallel_recorder = EvidenceRecorder.for_occurrences(
        authorizer,
        _evaluation_context(),
        producer_id="nornyx-lab.academy.langgraph.parallel",
    )
    parallel_calls: Counter[str] = Counter()

    def branch(name: str) -> Any:
        def execute(_state: Any) -> dict[str, int]:
            parallel_calls[name] += 1
            return {name: 1}

        return execute

    parallel_builder = graph.StateGraph(_ParallelState)
    for name in ("left", "right"):
        parallel_builder.add_node(
            name,
            _governed_node(
                dependencies,
                authorizer=authorizer,
                recorder=parallel_recorder,
                mission_id="mission.academy.lab19.parallel",
                action=branch(name),
            ),
        )
        parallel_builder.add_edge(graph.START, name)
        parallel_builder.add_edge(name, graph.END)
    parallel_output = parallel_builder.compile().invoke({})
    parallel = {
        "actual_framework_execution": True,
        "calls": dict(sorted(parallel_calls.items())),
        "output": {key: parallel_output.get(key) for key in ("left", "right")},
        **_occurrence_summary(parallel_recorder),
    }
    parallel["passed"] = (
        parallel["calls"] == {"left": 1, "right": 1}
        and parallel["output"] == {"left": 1, "right": 1}
        and parallel["distinct_occurrences"] == 2
        and parallel["attempts"] == (1,)
        and parallel["evidence"]["status"] == "pass"
    )

    interrupt_recorder = EvidenceRecorder.for_occurrences(
        authorizer,
        _evaluation_context(),
        producer_id="nornyx-lab.academy.langgraph.interrupt",
    )
    interrupt_calls = 0

    def pause(_state: Any) -> dict[str, str]:
        nonlocal interrupt_calls
        interrupt_calls += 1
        return {"answer": dependencies["types"].interrupt("human-approval")}

    interrupt_node = _governed_node(
        dependencies,
        authorizer=authorizer,
        recorder=interrupt_recorder,
        mission_id="mission.academy.lab19.interrupt",
        action=pause,
    )
    checkpointer = dependencies["memory"].InMemorySaver()
    interrupt_graph = _compile_single(dependencies, interrupt_node, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "academy-lab-19"}}
    interrupted = interrupt_graph.invoke({}, config)
    resumed = interrupt_graph.invoke(dependencies["types"].Command(resume="approved"), config)
    interrupt_result = {
        "actual_framework_execution": True,
        "calls": interrupt_calls,
        "interrupted": bool(interrupted.get("__interrupt__")),
        "resumed_answer": resumed.get("answer"),
        "interrupt_recorded_as_failure": False,
        **_occurrence_summary(interrupt_recorder),
    }
    interrupt_result["interrupt_recorded_as_failure"] = (
        interrupt_result["event_types"].get("runtime_failed", 0) > 0
    )
    interrupt_result["passed"] = (
        interrupt_result["calls"] == 2
        and interrupt_result["interrupted"] is True
        and interrupt_result["resumed_answer"] == "approved"
        and interrupt_result["distinct_occurrences"] == 1
        and interrupt_result["attempts"] == (1, 2)
        and interrupt_result["interrupt_recorded_as_failure"] is False
        and interrupt_result["evidence"]["status"] == "pass"
    )

    denial_recorder = EvidenceRecorder.for_occurrences(
        authorizer,
        _evaluation_context(),
        producer_id="nornyx-lab.academy.langgraph.denial",
    )
    denied_calls = 0

    def must_not_run(_state: Any) -> dict[str, int]:
        nonlocal denied_calls
        denied_calls += 1
        return {"value": 1}

    denied_node = _governed_node(
        dependencies,
        authorizer=authorizer,
        recorder=denial_recorder,
        mission_id="mission.academy.lab19.denial",
        action=must_not_run,
        identity_ref="identity.intake_agent",
        capability_ref="issue_refund",
    )
    denied_code = None
    try:
        _compile_single(dependencies, denied_node).invoke({})
    except dependencies["errors"].AdapterDenied as exc:
        denied_code = exc.decision.code.value
    denial = {
        "actual_framework_execution": True,
        "calls": denied_calls,
        "decision_effect": "deny" if denied_code else "indeterminate",
        "decision_code": denied_code,
        "counter": {
            "attempts": denied_calls,
            "completions": denied_calls,
            "meaning": "prevented_before_execution" if denied_calls == 0 else "executed",
        },
        **_occurrence_summary(denial_recorder),
    }
    denial["passed"] = (
        denial["calls"] == 0
        and denial["decision_code"] == "CAPABILITY_DENIED"
        and denial["distinct_occurrences"] == 1
        and denial["attempts"] == (1,)
        and denial["event_types"].get("capability_denied") == 1
        and denial["event_types"].get("agent_invoked", 0) == 0
        and denial["evidence"]["status"] == "pass"
    )

    return {
        "retry": retry,
        "loop": loop,
        "parallel": parallel,
        "interrupt_resume": interrupt_result,
        "authorization_denial": denial,
    }


def _langgraph_boundaries(dependencies: Mapping[str, Any]) -> dict[str, Any]:
    graph = dependencies["graph"]
    plain_calls = 0

    def unwrapped(_state: Any) -> dict[str, int]:
        nonlocal plain_calls
        plain_calls += 1
        return {"value": 1}

    builder = graph.StateGraph(_ValueState)
    builder.add_node("plain", unwrapped)
    builder.add_edge(graph.START, "plain")
    builder.add_edge("plain", graph.END)
    output = builder.compile().invoke({})

    authorizer = _authorizer("ledger")
    recorder = EvidenceRecorder.for_occurrences(
        authorizer,
        _evaluation_context(),
        producer_id="nornyx-lab.academy.langgraph.boundary",
    )

    async def unsupported_async(_state: Any) -> dict[str, int]:
        return {"value": 1}

    async_rejected = False
    try:
        _governed_node(
            dependencies,
            authorizer=authorizer,
            recorder=recorder,
            mission_id="mission.academy.lab19.async-probe",
            action=unsupported_async,
        )
    except dependencies["errors"].AdapterConfigurationError:
        async_rejected = True

    inventory = tuple(
        {
            "surface": entry.surface,
            "status": entry.status.value,
            "reason": entry.reason,
            "exercise": (
                "executed_governed_public_metadata"
                if entry.surface == "sync_node_invocation"
                else "executed_unwrapped_negative_control"
                if entry.surface == "graph_topology"
                else "construction_rejected"
                if entry.surface == "async_node_invocation"
                else "not_executed_declared_unsupported"
            ),
        }
        for entry in dependencies["adapter"].COVERAGE_INVENTORY.entries
    )
    return {
        "inventory": inventory,
        "unwrapped_topology_probe": {
            "actual_framework_execution": True,
            "output": output.get("value"),
            "executions": plain_calls,
            "nornyx_authorizations": 0,
            "nornyx_evidence_events": 0,
            "passed": output.get("value") == 1 and plain_calls == 1,
        },
        "async_wrapper_probe": {
            "action_executed": False,
            "construction_rejected": async_rejected,
            "passed": async_rejected,
        },
    }


def _run_19(values: Mapping[str, Any]) -> StructuredLabRun:
    _only(values, set())
    try:
        dependencies, unavailable_reason = _load_langgraph()
    except Exception:
        return _failed_19("dependency loading")
    if dependencies is None:
        assert unavailable_reason is not None
        return _unavailable_19(unavailable_reason)
    try:
        patterns = _langgraph_patterns(dependencies)
        boundaries = _langgraph_boundaries(dependencies)
    except Exception as exc:
        return _failed_19(type(exc).__name__)

    checks = {
        "exact_framework_pin": dependencies["version"] == _LANGGRAPH_VERSION,
        "exact_adapter_pin": dependencies["adapter_version"] == _LANGGRAPH_ADAPTER_VERSION,
        "retry_identity": bool(patterns["retry"]["passed"]),
        "loop_identity": bool(patterns["loop"]["passed"]),
        "parallel_identity": bool(patterns["parallel"]["passed"]),
        "interrupt_resume_identity": bool(patterns["interrupt_resume"]["passed"]),
        "authorization_denial_prevents_execution": bool(patterns["authorization_denial"]["passed"]),
        "unwrapped_topology_visible": bool(boundaries["unwrapped_topology_probe"]["passed"]),
        "unsupported_async_rejected": bool(boundaries["async_wrapper_probe"]["passed"]),
    }
    passed = all(checks.values())
    pattern_rows = tuple(
        {
            "pattern": name,
            "calls": outcome["calls"],
            "occurrences": outcome["distinct_occurrences"],
            "attempts": outcome["attempts"],
            "evidence": outcome["evidence"]["status"],
            "passed": outcome["passed"],
        }
        for name, outcome in patterns.items()
    )
    return StructuredLabRun(
        run_id=_run_id("19", values),
        module_id="19",
        legacy_lab_id="19",
        title="LangGraph Runtime Semantics and Coverage",
        status=RunStatus.COMPLETE if passed else RunStatus.FAILED,
        blocks=(
            _block(
                "lab-19-runtime",
                BlockKind.SECTION,
                title="Real LangGraph execution",
                body=(
                    "Five native StateGraph runs exercise the adapter through LangGraph's public "
                    "Runtime.execution_info metadata. Runtime-generated task identifiers are "
                    "counted but not exposed, keeping the browser result deterministic."
                ),
            ),
            _block(
                "lab-19-patterns",
                BlockKind.DECISION_TABLE,
                title="Retry, loop, parallel, interrupt/resume, and authorization denial",
                rows=pattern_rows,
            ),
            _block(
                "lab-19-coverage",
                BlockKind.DECISION_TABLE,
                title="Adapter coverage inventory",
                rows=boundaries["inventory"],
            ),
            _block(
                "lab-19-boundary",
                BlockKind.BOUNDARY,
                title="The exact assurance boundary",
                body=(
                    "Only explicitly wrapped synchronous StateGraph node callables are governed. "
                    "Graph topology is caller-owned and was exercised as an unwrapped bypass. "
                    "Async nodes are rejected; remote/distributed execution and subgraph or "
                    "ToolNode internals are unsupported, not silently covered. Occurrence metadata "
                    "and evidence continuity remain cooperative producer assertions."
                ),
            ),
            _block(
                "lab-19-verdict",
                BlockKind.VERDICT,
                title="Executable verdict",
                body=(
                    "All real framework and evidence checks passed."
                    if passed
                    else "One or more real framework checks failed; completion is closed."
                ),
                metadata={"passed": passed},
            ),
        ),
        results={
            "framework": {
                "name": "langgraph",
                "version": dependencies["version"],
                "adapter": "nornyx-agentic-adapters.langgraph",
                "adapter_version": dependencies["adapter_version"],
                "actual_execution": True,
                "fallback_used": False,
                "public_metadata": "Runtime.execution_info",
            },
            "patterns": patterns,
            "coverage": boundaries,
            "checks": checks,
        },
        executable_checks=tuple(checks),
        completion_eligible=passed,
        safety_boundary=(
            "All graphs, checkpoints, Nornyx recorders, and Northstar fixtures stayed in process "
            "and memory. No network, subprocess, repository mutation, credential, model, or "
            "external business effect was reachable."
        ),
    )


def _approval(action: str, state: str = "valid") -> ApprovalAssertion | None:
    if state == "missing":
        return None
    actor_type = "human" if state == "valid" else "autonomous_agent"
    return ApprovalAssertion(
        approval_ref="agentic_network_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type=actor_type,
        role="network_governance_owner",
        granted=True,
        action_ref=action,
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record", "agentic_network_contract_review"),
    )


def _governance_approval(action: str, state: str = "valid") -> ApprovalAssertion | None:
    """Build the candidate pack's separate delivery governance assertion."""

    if state == "missing":
        return None
    actor_type = "human" if state == "valid" else "autonomous_agent"
    return ApprovalAssertion(
        approval_ref="governance_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type=actor_type,
        role="reviewer",
        granted=True,
        action_ref=action,
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record",),
    )


def _counter(ledger: Ledger, action: str) -> dict[str, Any]:
    attempts = ledger.attempts(action)
    completions = ledger.completions(action)
    if attempts == completions == 0:
        meaning = "prevented_before_execution"
    elif attempts == completions and attempts > 0:
        meaning = "executed"
    elif attempts > completions:
        meaning = "attempted_not_completed"
    else:
        meaning = "indeterminate"
    return {
        "action": action,
        "attempts": attempts,
        "completions": completions,
        "meaning": meaning,
    }


def _record_capability(
    *,
    authorizer: Any,
    context: EvaluationContext,
    recorder: EvidenceRecorder,
    mission_id: str,
    identity: str,
    capability: str,
) -> Any:
    decision = authorizer.evaluate(CapabilityRequest(identity, capability), context=context)
    recorder.record_decision(decision, mission_id=mission_id)
    return decision


def _approval_gate(
    *,
    authorizer: Any,
    context: EvaluationContext,
    recorder: EvidenceRecorder,
    mission_id: str,
    identity: str,
    action: str,
    state: str,
) -> tuple[Any | None, ApprovalAssertion | None]:
    assertion = _approval(action, state)
    if assertion is None:
        return None, None
    decision = authorizer.evaluate(ApprovalRequest(identity, assertion), context=context)
    recorder.record_decision(decision, mission_id=mission_id)
    return decision, assertion


def _workflow_step(
    step_id: str,
    identity: str,
    capability: str,
    decision: Any,
    counter: Mapping[str, Any],
    *,
    prerequisite: str,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "identity": identity,
        "capability": capability,
        "nornyx_decision": _decision(decision),
        "prerequisite": prerequisite,
        "counter": dict(counter),
    }


def _forge_contract_document(evidence_hashes: Mapping[str, str]) -> dict[str, Any]:
    """Derive a complete Forge fixture from the checked candidate profile shape."""

    document = deepcopy(load_nyx(shared_contract("ledger") / "network.nyx"))
    document["project"].update(
        name="NorthstarForge",
        purpose="Governed multi-agent software delivery with maker-checker release controls.",
        non_goals=[
            "live source-control access",
            "agent orchestration",
            "agent authentication",
            "credential loading",
            "real merge or release execution",
            "automatic approvals",
        ],
    )
    document["intents"] = [
        {
            "name": "GovernSoftwareDelivery",
            "goal": "Author, test, review, merge, and publish releases with separate authorities.",
        }
    ]
    document["goals"] = [
        {
            "id": "GOAL-FORGE-001",
            "title": "Operate the governed Forge delivery network",
            "phase": "ACADEMY-LAB-22",
            "goal": "Ship one reviewed, tested, human-approved inert release.",
            "scope": ["network.nyx", "governance_evidence/"],
            "non_goals": ["live repository access", "real merge", "real package publication"],
            "validation": [
                "direct Python contract check at the pinned validation time",
                "direct Python agentic-network lock verification",
            ],
            "evidence": "governance_evidence/",
            "approval": "required before merge and release at the exact subject revision",
            "stop_rules": [
                "stop on identity, capability, approval, evidence, or revision ambiguity",
                "stop before any external repository or release effect",
            ],
        }
    ]
    document["contexts"] = [
        {
            "name": "DeliveryContext",
            "include": ["README.md", "src/**/*.py", "tests/**/*.py"],
            "exclude": [".env", "secrets/**", "release_credentials/**"],
            "authority": ["network.nyx"],
            "budget": {"max_tokens": 32000, "reserve_output_tokens": 4000},
        }
    ]
    document["agents"] = [
        {
            "name": "ForgeAuthor",
            "role": "Author a bounded patch; never review, merge, or release it.",
            "policy": "ForgeGovernance",
        },
        {
            "name": "ForgeReviewer",
            "role": "Run delegated tests and independently review the patch; never merge it.",
            "policy": "ForgeGovernance",
        },
        {
            "name": "ForgeReleaseAgent",
            "role": "Execute only approved merge and release transitions.",
            "policy": "ForgeGovernance",
        },
        {
            "name": "ForgeApprovalRouter",
            "role": "Route human approval and close the release record; never grant approval.",
            "policy": "ForgeGovernance",
        },
    ]
    document["policies"] = [
        {
            "name": "ForgeGovernance",
            "deny": [
                "autonomous_approval",
                "self_review",
                "undeclared_capability_use",
                "unreviewed_merge",
            ],
            "require": [
                "exact_revision_binding",
                "independent_review_before_merge",
                "human_approval_before_merge",
                "evidence_before_release",
            ],
        }
    ]

    def capability(
        name: str,
        action: str,
        *,
        risk: str,
        gate: str | None = None,
        approval: bool = False,
        evidence: bool = False,
        delegable: bool = False,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": name,
            "actions": [action],
            "risk": risk,
            "scope_type": "context",
            "scope_refs": ["DeliveryContext"],
            "delegable": delegable,
            "required_gate_refs": [gate] if gate else [],
            "required_approval_refs": ["agentic_network_authority"] if approval else [],
            "required_evidence_refs": ["agentic_network_contract_review"] if evidence else [],
        }
        if delegable:
            item["max_delegation_depth"] = 1
        return item

    document["capabilities"] = [
        capability("read_repository", "read_repository", risk="low"),
        capability(
            "author_patch", "author_patch", risk="medium", gate="gate.change_review", evidence=True
        ),
        capability(
            "run_tests",
            "run_tests",
            risk="low",
            gate="gate.change_review",
            evidence=True,
            delegable=True,
        ),
        capability(
            "review_patch", "review_patch", risk="medium", gate="gate.change_review", evidence=True
        ),
        capability(
            "merge_pull_request",
            "merge",
            risk="high",
            gate="gate.merge_review",
            approval=True,
            evidence=True,
        ),
        capability(
            "publish_release",
            "release",
            risk="high",
            gate="gate.release_publication",
            approval=True,
            evidence=True,
        ),
        capability("request_human_approval", "request_approval", risk="low"),
        capability("close_release", "close_release", risk="low"),
    ]

    def identity(
        identity_ref: str,
        role_ref: str,
        subject: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        return {
            "id": identity_ref,
            "role_ref": role_ref,
            "identity_class": "local_agent",
            "namespace": f"forge.{subject}",
            "subject": subject,
            "framework_bindings": [
                {"framework": "contract_fixture", "agent_key": subject},
                {"framework": "langgraph", "agent_key": subject},
            ],
            "capability_refs": capabilities,
            "status": "active",
            "valid_from": "2026-01-01T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z",
            "revocation_refs": [],
            "authority": "non_human",
            "can_approve": False,
        }

    document["agent_identities"] = [
        identity(
            "identity.forge_author",
            "ForgeAuthor",
            "author",
            ["read_repository", "author_patch", "run_tests"],
        ),
        identity(
            "identity.forge_reviewer",
            "ForgeReviewer",
            "reviewer",
            ["read_repository", "review_patch"],
        ),
        identity(
            "identity.forge_release_agent",
            "ForgeReleaseAgent",
            "release_agent",
            ["read_repository", "merge_pull_request", "publish_release"],
        ),
        identity(
            "identity.forge_approval_router",
            "ForgeApprovalRouter",
            "approval_router",
            ["request_human_approval", "close_release"],
        ),
    ]
    approval = document["approvals"][0]
    approval["required_for"] = [
        "approve_agentic_network_contract",
        "external_share",
        "merge",
        "release",
        "handoff",
    ]

    for record in document["governance_evidence"]["records"]:
        artifact = str(record["artifact"])
        record["content_hash"] = evidence_hashes[artifact]

    network = document["agentic_network"]
    network["id"] = "network.northstar_forge"
    network["trust_zones"] = [
        {
            "id": "zone.forge_branch",
            "classification": "governed_local",
            "allowed_transition_targets": ["zone.main_branch"],
            "share_allowlist": ["patch", "test_report", "review_record", "evidence_digest"],
            "never_share": ["secrets", "credentials", "tokens", "private_memory"],
            "ingress_gate_refs": [],
            "egress_gate_refs": ["gate.merge_review"],
        },
        {
            "id": "zone.main_branch",
            "classification": "governed_local",
            "allowed_transition_targets": ["zone.release_channel"],
            "share_allowlist": [
                "patch",
                "test_report",
                "review_record",
                "release_artifact",
                "release_notes",
                "evidence_digest",
            ],
            "never_share": ["secrets", "credentials", "tokens", "private_memory"],
            "ingress_gate_refs": ["gate.merge_review"],
            "egress_gate_refs": ["gate.release_publication"],
        },
        {
            "id": "zone.release_channel",
            "classification": "external_contract_only",
            "allowed_transition_targets": [],
            "share_allowlist": ["release_artifact", "release_notes", "evidence_digest"],
            "never_share": ["secrets", "credentials", "tokens", "private_memory"],
            "ingress_gate_refs": ["gate.release_publication"],
            "egress_gate_refs": [],
        },
    ]

    def membership(
        membership_id: str,
        identity_ref: str,
        zone: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        return {
            "id": membership_id,
            "identity_ref": identity_ref,
            "trust_zone_ref": zone,
            "capability_refs": capabilities,
            "status": "authorized",
            "valid_from": "2026-01-01T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z",
            "revocation_refs": [],
        }

    network["memberships"] = [
        membership(
            "membership.forge_author",
            "identity.forge_author",
            "zone.forge_branch",
            ["read_repository", "author_patch", "run_tests"],
        ),
        membership(
            "membership.forge_reviewer",
            "identity.forge_reviewer",
            "zone.forge_branch",
            ["read_repository", "review_patch"],
        ),
        membership(
            "membership.forge_release_branch",
            "identity.forge_release_agent",
            "zone.forge_branch",
            ["read_repository", "merge_pull_request"],
        ),
        membership(
            "membership.forge_release_main",
            "identity.forge_release_agent",
            "zone.main_branch",
            ["read_repository", "merge_pull_request", "publish_release"],
        ),
        membership(
            "membership.forge_approval_router",
            "identity.forge_approval_router",
            "zone.forge_branch",
            ["request_human_approval", "close_release"],
        ),
    ]
    network["protocol_targets"] = [
        {
            "id": "protocol.release_publication",
            "protocol": "mcp",
            "version": "declared-by-project",
            "execution_mode": "contract_only",
            "live_connector_execution": False,
            "identity_refs": ["identity.forge_release_agent"],
            "source_membership_refs": ["membership.forge_release_main"],
            "source_zone_ref": "zone.main_branch",
            "capability_refs": ["publish_release"],
            "trust_zone_ref": "zone.release_channel",
            "share": ["release_artifact", "release_notes", "evidence_digest"],
            "never_share": ["secrets", "credentials", "tokens", "private_memory"],
            "required_gate_refs": ["gate.release_publication"],
            "required_approval_refs": ["agentic_network_authority"],
            "required_evidence_refs": ["agentic_network_contract_review"],
        }
    ]
    network["network_gates"] = [
        {
            "id": "gate.change_review",
            "action_classes": ["author_patch", "run_tests", "review_patch"],
            "source_zone_refs": ["zone.forge_branch"],
            "target_zone_refs": ["zone.forge_branch"],
            "required_policy_refs": ["ForgeGovernance"],
            "required_approval_refs": [],
            "required_evidence_refs": ["agentic_network_contract_review"],
        },
        {
            "id": "gate.merge_review",
            "action_classes": ["merge", "handoff"],
            "source_zone_refs": ["zone.forge_branch"],
            "target_zone_refs": ["zone.main_branch"],
            "required_policy_refs": ["ForgeGovernance"],
            "required_approval_refs": ["agentic_network_authority"],
            "required_evidence_refs": ["agentic_network_contract_review"],
        },
        {
            "id": "gate.release_publication",
            "action_classes": ["release", "external_share"],
            "source_zone_refs": ["zone.main_branch"],
            "target_zone_refs": ["zone.release_channel"],
            "required_policy_refs": ["ForgeGovernance"],
            "required_approval_refs": ["agentic_network_authority"],
            "required_evidence_refs": ["agentic_network_contract_review"],
        },
    ]
    network["revocations"] = []
    network["delegations"] = [
        {
            "id": "delegation.forge_test_run",
            "delegator_ref": "identity.forge_author",
            "delegate_ref": "identity.forge_reviewer",
            "capability_ref": "run_tests",
            "purpose": "Delegate an independent execution of the test suite to the reviewer.",
            "actions": ["run_tests"],
            "scope_refs": ["DeliveryContext"],
            "status": "active",
            "valid_from": "2026-01-01T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z",
            "max_depth": 1,
            "current_depth": 0,
            "onward_delegation": "denied",
            "source_zone_ref": "zone.forge_branch",
            "target_zone_ref": "zone.forge_branch",
            "required_gate_refs": ["gate.change_review"],
            "required_policy_refs": ["ForgeGovernance"],
            "required_approval_refs": [],
            "required_evidence_refs": ["agentic_network_contract_review"],
            "revocation_refs": [],
        }
    ]
    network["handoffs"] = [
        {
            "id": "handoff.forge_release",
            "from_identity_ref": "identity.forge_author",
            "to_identity_ref": "identity.forge_release_agent",
            "purpose": "Transfer a reviewed change to the release authority for approved merge.",
            "mission_ref": "GOAL-FORGE-001",
            "from_zone_ref": "zone.forge_branch",
            "to_zone_ref": "zone.main_branch",
            "required_capability_refs": ["merge_pull_request"],
            "delegation_refs": [],
            "shared_context": ["patch", "test_report", "review_record"],
            "never_share": ["secrets", "credentials", "tokens", "private_memory"],
            "status": "initiated",
            "valid_from": "2026-01-01T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z",
            "required_gate_refs": ["gate.merge_review"],
            "required_approval_refs": ["agentic_network_authority"],
            "required_evidence_refs": ["agentic_network_contract_review"],
            "revocation_refs": [],
        }
    ]
    network["relations"] = [
        {
            "id": "relation.forge_test_delegation",
            "type": "delegates_to",
            "source": {"kind": "agent_identity", "ref": "identity.forge_author"},
            "target": {"kind": "agent_identity", "ref": "identity.forge_reviewer"},
            "delegation_ref": "delegation.forge_test_run",
        },
        {
            "id": "relation.forge_release_handoff",
            "type": "hands_off_to",
            "source": {"kind": "agent_identity", "ref": "identity.forge_author"},
            "target": {"kind": "agent_identity", "ref": "identity.forge_release_agent"},
            "handoff_ref": "handoff.forge_release",
        },
        {
            "id": "relation.forge_merge_approval",
            "type": "requires_approval_from",
            "source": {"kind": "capability", "ref": "merge_pull_request"},
            "target": {"kind": "human_role", "ref": "network_governance_owner"},
        },
        {
            "id": "relation.forge_release_advertisement",
            "type": "advertises_capability",
            "source": {"kind": "agent_identity", "ref": "identity.forge_release_agent"},
            "target": {"kind": "capability", "ref": "publish_release"},
        },
    ]
    return document


@lru_cache(maxsize=1)
def _forge_kit() -> tuple[Any, dict[str, Any]]:
    """Build and load a temporary lock-verified Forge contract through public APIs."""

    evidence_payloads = {
        "governance_evidence/evidence_manifest.json": {
            "evidence_type": "evidence_manifest",
            "scope": "governed Forge delivery network",
            "status": "pass",
            "subject_revision": LAB_SUBJECT_REVISION,
        },
        "governance_evidence/independent_review_record.json": {
            "evidence_type": "network_contract_review",
            "reviewer_role": "security_reviewer",
            "status": "pass",
            "subject_revision": LAB_SUBJECT_REVISION,
            "summary": "Static review of the deterministic Forge academy contract.",
        },
        "governance_evidence/approval_record.json": {
            "actor_type": "human",
            "approver_role": "network_governance_owner",
            "evidence_type": "approval_record",
            "scope": "approve_agentic_network_contract",
            "status": "pass",
            "subject_revision": LAB_SUBJECT_REVISION,
        },
    }
    evidence_bytes = {
        name: json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        for name, payload in evidence_payloads.items()
    }
    evidence_hashes = {
        name: "sha256:" + hashlib.sha256(raw).hexdigest() for name, raw in evidence_bytes.items()
    }
    document = _forge_contract_document(evidence_hashes)

    with tempfile.TemporaryDirectory(prefix="nornyx-academy-forge-") as temporary:
        root = Path(temporary)
        for name, raw in evidence_bytes.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        contract = root / "network.nyx"
        contract.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        registry = registry_for_contract(contract)
        loaded = load_nyx(contract)
        diagnostics = list(check_document(loaded))
        composition = compose_document_governance(loaded, registry=registry)
        if composition is None:
            raise RuntimeError("Forge contract did not resolve its declared governance profile")
        contributed = {item.block for item in (composition.block_schemas or ())}
        diagnostics = [
            item
            for item in diagnostics
            if not (
                getattr(item, "code", None) == "UNKNOWN_TOP_LEVEL_BLOCK"
                and getattr(item, "path", None) in contributed
            )
        ]
        diagnostics.extend(
            evaluate_document_governance(
                loaded,
                registry=registry,
                as_of=LAB_AS_OF,
                document_root=root,
            )
        )
        errors = [item for item in diagnostics if getattr(item, "level", None) == "error"]
        if errors:
            codes = ", ".join(sorted({str(getattr(item, "code", "ERROR")) for item in errors}))
            raise RuntimeError(f"Forge contract validation failed: {codes}")
        artifacts = root / "control_artifacts"
        artifacts.mkdir()
        for name, raw in render_agentic_network_artifacts(loaded, composition).items():
            (artifacts / name).write_bytes(raw)
        lock_payload = build_agentic_network_lock(loaded, composition)
        lock_path = root / "nornyx.agentic_network.lock"
        write_agentic_network_lock(lock_payload, lock_path)
        authorizer = load_authorizer(contract, lock_path, validation_as_of=LAB_AS_OF)
    return authorizer, loaded


def _run_22(values: Mapping[str, Any]) -> StructuredLabRun:
    _only(values, {"approval_state", "include_inert_bypass"})
    approval_state = _choice(
        values.get("approval_state"),
        name="approval_state",
        default="valid",
        choices={"valid", "missing", "non_human"},
    )
    include_bypass = _boolean(
        values.get("include_inert_bypass"), name="include_inert_bypass", default=True
    )

    authorizer = _authorizer("ledger")
    context = _evaluation_context()
    recorder = EvidenceRecorder(
        authorizer,
        context,
        producer_id="nornyx-lab.academy.multi-agent",
    )
    mission_id = "mission.academy.lab22"
    ledger = Ledger("academy-lab22-governed")
    workflow: list[dict[str, Any]] = []

    read = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.intake_agent",
        capability="read_customer_case",
    )
    if read.allowed:
        northstar.read_case(ledger, "CASE-1041")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.intake_agent",
            capability_ref="read_customer_case",
        )
    workflow.append(
        _workflow_step(
            "intake",
            "identity.intake_agent",
            "read_customer_case",
            read,
            _counter(ledger, "read_case"),
            prerequisite="declared membership and capability",
        )
    )

    analyze = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.case_analyst",
        capability="analyze_case",
    )
    if analyze.allowed:
        northstar.analyze_case(ledger, "CASE-1041")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.case_analyst",
            capability_ref="analyze_case",
        )
    workflow.append(
        _workflow_step(
            "analysis",
            "identity.case_analyst",
            "analyze_case",
            analyze,
            _counter(ledger, "analyze_case"),
            prerequisite="intake result handed to a distinct analyst identity",
        )
    )

    delegation = authorizer.evaluate(
        DelegationRequest("delegation.refund_proposal"), context=context
    )
    recorder.record_decision(delegation, mission_id=mission_id)
    proposal = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.remediation_agent",
        capability="propose_refund",
    )
    if delegation.allowed and proposal.allowed:
        ledger.attempt("propose_refund", case="CASE-1041")
        ledger.complete("propose_refund", amount=5000.0)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.remediation_agent",
            capability_ref="propose_refund",
            delegation_ref="delegation.refund_proposal",
        )
    workflow.append(
        _workflow_step(
            "delegated-proposal",
            "identity.remediation_agent",
            "propose_refund",
            proposal,
            _counter(ledger, "propose_refund"),
            prerequisite="bounded declared delegation from identity.case_analyst",
        )
    )

    approval_request = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.compliance_officer",
        capability="request_human_approval",
    )
    if approval_request.allowed:
        recorder.record_observation(
            "agent_invoked",
            mission_id=mission_id,
            actor_ref="identity.compliance_officer",
            capability_ref="request_human_approval",
        )

    refund_approval, _refund_assertion = _approval_gate(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.remediation_agent",
        action="issue_refund",
        state=approval_state,
    )
    refund_capability = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.remediation_agent",
        capability="issue_refund",
    )
    refund_gate_open = bool(
        refund_capability.allowed
        and refund_approval is not None
        and refund_approval.allowed
        and proposal.allowed
    )
    if refund_gate_open:
        northstar.issue_refund(ledger, 5000.0)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.remediation_agent",
            capability_ref="issue_refund",
        )
    workflow.append(
        _workflow_step(
            "disbursement",
            "identity.remediation_agent",
            "issue_refund",
            refund_capability,
            _counter(ledger, "issue_refund"),
            prerequisite=(
                "application conjunction: capability allowance AND separately validated human "
                "approval; ApprovalRequest does not mutate or unlock Authorizer state"
            ),
        )
    )

    handoff = authorizer.evaluate(HandoffRequest("handoff.compliance_closure"), context=context)
    recorder.record_decision(handoff, mission_id=mission_id)
    handoff_approval, _handoff_assertion = _approval_gate(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.intake_agent",
        action="handoff",
        state=approval_state,
    )
    handoff_gate_open = bool(
        refund_gate_open
        and handoff.allowed
        and handoff_approval is not None
        and handoff_approval.allowed
    )
    if handoff_gate_open:
        ledger.attempt("handoff", target="identity.compliance_officer")
        recorder.record_observation(
            "handoff_initiated",
            mission_id=mission_id,
            actor_ref="identity.intake_agent",
            target_ref="identity.compliance_officer",
            handoff_ref="handoff.compliance_closure",
        )
        ledger.complete("handoff", target="identity.compliance_officer")
        recorder.record_observation(
            "handoff_completed",
            mission_id=mission_id,
            actor_ref="identity.compliance_officer",
            target_ref="identity.compliance_officer",
            handoff_ref="handoff.compliance_closure",
        )

    close = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.compliance_officer",
        capability="close_case",
    )
    if handoff_gate_open and close.allowed:
        ledger.attempt("close_case", case="CASE-1041")
        ledger.complete("close_case", case="CASE-1041")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.compliance_officer",
            capability_ref="close_case",
        )
    workflow.append(
        _workflow_step(
            "compliance-closure",
            "identity.compliance_officer",
            "close_case",
            close,
            _counter(ledger, "close_case"),
            prerequisite="declared handoff and separately validated handoff approval",
        )
    )

    notice_capability = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.remediation_agent",
        capability="notify_customer_external",
    )
    notice_assertion = _approval("notify_customer", approval_state)
    notice_crossing = authorizer.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
            notice_assertion,
        ),
        context=context,
    )
    recorder.record_decision(notice_crossing, mission_id=mission_id)
    notice_gate_open = bool(
        handoff_gate_open and notice_capability.allowed and notice_crossing.allowed
    )
    if notice_gate_open:
        northstar.notify_customer(ledger, "Your approved remediation is complete.")
        recorder.record_observation(
            "trust_zone_crossed",
            mission_id=mission_id,
            actor_ref="identity.remediation_agent",
            source_zone_ref="zone.remediation_internal",
            target_zone_ref="zone.customer_channel",
        )
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.remediation_agent",
            capability_ref="notify_customer_external",
        )
    workflow.append(
        _workflow_step(
            "customer-notice",
            "identity.remediation_agent",
            "notify_customer_external",
            notice_capability,
            _counter(ledger, "notify_customer"),
            prerequisite=("real combined ZoneCrossingRequest with an action-scoped human approval"),
        )
    )

    identities = (
        "identity.intake_agent",
        "identity.case_analyst",
        "identity.remediation_agent",
        "identity.compliance_officer",
    )
    required_capabilities = (
        "read_customer_case",
        "analyze_case",
        "propose_refund",
        "issue_refund",
        "close_case",
        "notify_customer_external",
    )
    separation = []
    for identity in identities:
        holdings = {
            capability: authorizer.evaluate(
                CapabilityRequest(identity, capability), context=context
            ).allowed
            for capability in required_capabilities
        }
        separation.append(
            {
                "identity": identity,
                "capabilities": holdings,
                "can_complete_alone": all(holdings.values()),
            }
        )

    document = load_nyx(shared_contract("ledger") / "network.nyx")
    agent_identities = tuple(document.get("agent_identities", ()))
    approval_authority = {
        "identity_count": len(agent_identities),
        "all_non_human": all(item.get("authority") == "non_human" for item in agent_identities),
        "no_agent_can_approve": all(item.get("can_approve") is False for item in agent_identities),
        "compliance_may_request_not_grant": approval_request.allowed,
    }

    incident_denial = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.intake_agent",
        capability="issue_refund",
    )
    incident_ledger = Ledger("academy-lab22-incident")
    missing_crossing = authorizer.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
        ),
        context=context,
    )
    recorder.record_decision(missing_crossing, mission_id=mission_id)

    bypass_ledger = Ledger("academy-lab22-uncontrolled-bypass")
    if include_bypass:
        northstar.issue_refund(bypass_ledger, 5000.0)
    incident = {
        "unauthorized_identity": {
            "decision": _decision(incident_denial),
            "counter": _counter(incident_ledger, "issue_refund"),
        },
        "missing_customer_notice_approval": {
            "decision": _decision(missing_crossing),
            "counter": _counter(incident_ledger, "notify_customer"),
        },
        "direct_in_process_bypass": {
            "executed": include_bypass,
            "counter": _counter(bypass_ledger, "issue_refund"),
            "nornyx_decisions": 0,
            "coverage": "uncontrolled cooperative-boundary bypass",
            "external_effect": False,
        },
    }

    evidence = _evidence_summary(recorder)
    checks = {
        "distinct_identities_executed": len({step["identity"] for step in workflow}) == 4,
        "delegation_allowed": delegation.allowed and proposal.allowed,
        "handoff_allowed": handoff.allowed,
        "separation_of_duties": all(not row["can_complete_alone"] for row in separation),
        "agent_approval_prohibited": all(approval_authority.values()),
        "human_approval_validated": bool(refund_approval is not None and refund_approval.allowed),
        "combined_zone_crossing_allowed": notice_crossing.allowed,
        "happy_path_inert_effects": (
            ledger.completions("issue_refund") == 1
            and ledger.completions("close_case") == 1
            and ledger.completions("notify_customer") == 1
        ),
        "unauthorized_failure_prevented": (
            not incident_denial.allowed
            and incident_ledger.attempts("issue_refund") == 0
            and incident_ledger.completions("issue_refund") == 0
        ),
        "missing_approval_prevented_notice": (
            missing_crossing.effect.value == "approval_required"
            and incident_ledger.attempts("notify_customer") == 0
        ),
        "inert_bypass_visible": (
            include_bypass
            and bypass_ledger.attempts("issue_refund") == 1
            and bypass_ledger.completions("issue_refund") == 1
        ),
        "evidence_valid": evidence["status"] == "pass",
    }
    passed = all(checks.values())
    return StructuredLabRun(
        run_id=_run_id(
            "22",
            {"approval_state": approval_state, "include_inert_bypass": include_bypass},
        ),
        module_id="22",
        legacy_lab_id="22",
        title="Executable Multi-Agent Operations and Incident Reconstruction",
        status=RunStatus.COMPLETE if passed else RunStatus.FAILED,
        blocks=(
            _block(
                "lab-22-workflow",
                BlockKind.DECISION_TABLE,
                title="Four-identity deterministic workflow",
                rows=tuple(workflow),
            ),
            _block(
                "lab-22-separation",
                BlockKind.DECISION_TABLE,
                title="Separation of duties",
                body="Every row is evaluated by the real lock-verified Authorizer.",
                rows=tuple(separation),
            ),
            _block(
                "lab-22-incident",
                BlockKind.LEDGER_COMPARISON,
                title="Failure and bypass reconstruction",
                rows=tuple({"path": name, **details} for name, details in incident.items()),
            ),
            _block(
                "lab-22-boundary",
                BlockKind.BOUNDARY,
                title="Approval and enforcement boundaries",
                body=(
                    "CapabilityRequest checks holdings; it does not consume approval metadata. "
                    "ApprovalRequest validates an assertion but does not mutate or unlock the "
                    "Authorizer. This exercise therefore exposes the application's explicit AND "
                    "gate for internal disbursement. The customer-channel crossing uses the real "
                    "combined ZoneCrossingRequest approval path. All controls remain cooperative "
                    "and a direct in-process inert callable demonstrates the bypass."
                ),
            ),
            _block(
                "lab-22-verdict",
                BlockKind.VERDICT,
                title="Executable verdict",
                body=(
                    "The multi-agent workflow, negative controls, and evidence checks passed."
                    if passed
                    else "A workflow or assurance check failed; completion is closed."
                ),
                metadata={"passed": passed},
            ),
        ),
        results={
            "configuration": {
                "approval_state": approval_state,
                "include_inert_bypass": include_bypass,
            },
            "workflow": tuple(workflow),
            "delegation": _decision(delegation),
            "handoff": {
                "decision": _decision(handoff),
                "approval": _decision(handoff_approval) if handoff_approval else None,
                "counter": _counter(ledger, "handoff"),
            },
            "approvals": {
                "authority": approval_authority,
                "internal_refund": {
                    "assertion": approval_state,
                    "validation": _decision(refund_approval) if refund_approval else None,
                    "composition": "application_explicit_conjunction",
                    "authorizer_state_mutated": False,
                },
                "customer_notice": {
                    "assertion": approval_state,
                    "crossing": _decision(notice_crossing),
                    "composition": "nornyx_zone_crossing_request",
                },
            },
            "separation_of_duties": tuple(separation),
            "incident": incident,
            "governed_counters": tuple(
                _counter(ledger, action)
                for action in (
                    "read_case",
                    "analyze_case",
                    "propose_refund",
                    "issue_refund",
                    "handoff",
                    "close_case",
                    "notify_customer",
                )
            ),
            "evidence": evidence,
            "checks": checks,
        },
        executable_checks=tuple(checks),
        completion_eligible=passed,
        safety_boundary=(
            "Northstar read, analysis, refund, handoff, close, and notification functions are "
            "deterministic in-memory fixtures. No network, subprocess, repository mutation, "
            "credential, payment, email, or other external effect occurred."
        ),
    )


def _run_forge_22(values: Mapping[str, Any]) -> StructuredLabRun:
    """Execute the catalog's Forge author/reviewer/release network."""

    _only(values, {"approval_state", "include_inert_bypass"})
    approval_state = _choice(
        values.get("approval_state"),
        name="approval_state",
        default="valid",
        choices={"valid", "missing", "non_human"},
    )
    include_bypass = _boolean(
        values.get("include_inert_bypass"), name="include_inert_bypass", default=True
    )
    authorizer, forge_document = _forge_kit()
    context = _evaluation_context()
    recorder = EvidenceRecorder(
        authorizer,
        context,
        producer_id="nornyx-lab.academy.forge",
        producer_type="synthetic_harness",
    )
    mission_id = "mission.academy.lab22.forge"
    ledger = Ledger("academy-lab22-forge")
    workflow: list[dict[str, Any]] = []

    read = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_author",
        capability="read_repository",
    )
    if read.allowed:
        ledger.attempt("read_repository", ref="issue/77")
        ledger.complete("read_repository", files=3)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_author",
            capability_ref="read_repository",
        )
    workflow.append(
        _workflow_step(
            "read",
            "identity.forge_author",
            "read_repository",
            read,
            _counter(ledger, "read_repository"),
            prerequisite="declared branch membership",
        )
    )

    author_patch = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_author",
        capability="author_patch",
    )
    if read.allowed and author_patch.allowed:
        ledger.attempt("author_patch", files=2)
        ledger.complete("author_patch", patch_id="patch-77")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_author",
            capability_ref="author_patch",
        )
    workflow.append(
        _workflow_step(
            "author",
            "identity.forge_author",
            "author_patch",
            author_patch,
            _counter(ledger, "author_patch"),
            prerequisite="repository read completed on a reversible branch",
        )
    )

    delegation = authorizer.evaluate(
        DelegationRequest("delegation.forge_test_run"), context=context
    )
    recorder.record_decision(delegation, mission_id=mission_id)
    delegated_tests = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_reviewer",
        capability="run_tests",
    )
    if author_patch.allowed and delegation.allowed and delegated_tests.allowed:
        ledger.attempt("run_tests", suite="academy-fixture")
        ledger.complete("run_tests", passed=128, failed=0)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_reviewer",
            capability_ref="run_tests",
            delegation_ref="delegation.forge_test_run",
        )
    workflow.append(
        _workflow_step(
            "test",
            "identity.forge_reviewer",
            "run_tests",
            delegated_tests,
            _counter(ledger, "run_tests"),
            prerequisite="bounded one-hop delegation from the patch author",
        )
    )

    review = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_reviewer",
        capability="review_patch",
    )
    if ledger.completions("run_tests") == 1 and review.allowed:
        ledger.attempt("review_patch", patch_id="patch-77")
        ledger.complete("review_patch", finding="approved")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_reviewer",
            capability_ref="review_patch",
        )
    workflow.append(
        _workflow_step(
            "independent-review",
            "identity.forge_reviewer",
            "review_patch",
            review,
            _counter(ledger, "review_patch"),
            prerequisite="tests passed; reviewer is distinct from author and release agent",
        )
    )

    approval_route = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_approval_router",
        capability="request_human_approval",
    )
    if approval_route.allowed:
        recorder.record_observation(
            "agent_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_approval_router",
            capability_ref="request_human_approval",
        )

    handoff = authorizer.evaluate(HandoffRequest("handoff.forge_release"), context=context)
    recorder.record_decision(handoff, mission_id=mission_id)
    merge_assertion = _governance_approval("merge", approval_state)
    merge_approval = None
    if merge_assertion is not None:
        merge_approval = authorizer.evaluate(
            ApprovalRequest("identity.forge_release_agent", merge_assertion), context=context
        )
    handoff_open = bool(
        ledger.completions("review_patch") == 1
        and handoff.allowed
        and merge_approval is not None
        and merge_approval.allowed
    )
    if handoff_open:
        ledger.attempt("handoff", patch_id="patch-77")
        recorder.record_observation(
            "handoff_initiated",
            mission_id=mission_id,
            actor_ref="identity.forge_author",
            target_ref="identity.forge_release_agent",
            handoff_ref="handoff.forge_release",
        )
        ledger.complete("handoff", target="identity.forge_release_agent")
        recorder.record_observation(
            "handoff_completed",
            mission_id=mission_id,
            actor_ref="identity.forge_release_agent",
            target_ref="identity.forge_release_agent",
            handoff_ref="handoff.forge_release",
        )

    merge_capability = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_release_agent",
        capability="merge_pull_request",
    )
    merge_open = bool(
        handoff_open
        and merge_capability.allowed
        and merge_approval is not None
        and merge_approval.allowed
        and ledger.completions("run_tests") == 1
        and ledger.completions("review_patch") == 1
    )
    if merge_open:
        northstar.merge_pull_request(ledger, "PR-77", tests_passed=True)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_release_agent",
            capability_ref="merge_pull_request",
        )
    workflow.append(
        _workflow_step(
            "merge",
            "identity.forge_release_agent",
            "merge_pull_request",
            merge_capability,
            _counter(ledger, "merge_pull_request"),
            prerequisite=(
                "application conjunction: delegated tests + independent review + handoff + "
                "separately validated human approval"
            ),
        )
    )

    release_capability = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_release_agent",
        capability="publish_release",
    )
    release_assertion = _approval("release", approval_state)
    release_crossing = authorizer.evaluate(
        ZoneCrossingRequest(
            "identity.forge_release_agent",
            "zone.main_branch",
            "zone.release_channel",
            release_assertion,
        ),
        context=context,
    )
    recorder.record_decision(release_crossing, mission_id=mission_id)
    release_open = bool(
        ledger.completions("merge_pull_request") == 1
        and release_capability.allowed
        and release_crossing.allowed
    )
    if release_open:
        ledger.attempt("publish_release", version="2.0.0-academy")
        ledger.complete("publish_release", channel="inert-fixture")
        recorder.record_observation(
            "trust_zone_crossed",
            mission_id=mission_id,
            actor_ref="identity.forge_release_agent",
            source_zone_ref="zone.main_branch",
            target_zone_ref="zone.release_channel",
            approval_ref="agentic_network_authority",
        )
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_release_agent",
            capability_ref="publish_release",
        )
    workflow.append(
        _workflow_step(
            "release",
            "identity.forge_release_agent",
            "publish_release",
            release_capability,
            _counter(ledger, "publish_release"),
            prerequisite="real action-scoped ZoneCrossingRequest human-approval path",
        )
    )

    close = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.forge_approval_router",
        capability="close_release",
    )
    if release_open and close.allowed:
        ledger.attempt("close_release", version="2.0.0-academy")
        ledger.complete("close_release", status="evidence-bound")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.forge_approval_router",
            capability_ref="close_release",
        )
    workflow.append(
        _workflow_step(
            "close",
            "identity.forge_approval_router",
            "close_release",
            close,
            _counter(ledger, "close_release"),
            prerequisite="release crossing completed and evidence remained valid",
        )
    )

    agent_identities = tuple(forge_document.get("agent_identities", ()))
    authority = {
        "agent_identity_count": len(agent_identities),
        "all_agents_non_human": all(
            item.get("authority") == "non_human" for item in agent_identities
        ),
        "no_agent_can_approve": all(item.get("can_approve") is False for item in agent_identities),
        "human_governance_owner": "human.network_governance_owner",
        "human_owner_is_not_an_agent": all(
            item.get("id") != "human.network_governance_owner" for item in agent_identities
        ),
        "router_may_request_not_grant": approval_route.allowed,
    }
    required_capabilities = (
        "author_patch",
        "run_tests",
        "review_patch",
        "merge_pull_request",
        "publish_release",
        "close_release",
    )
    separation = []
    for item in agent_identities:
        identity_ref = str(item["id"])
        holdings = {
            capability: authorizer.evaluate(
                CapabilityRequest(identity_ref, capability), context=context
            ).allowed
            for capability in required_capabilities
        }
        separation.append(
            {
                "identity": identity_ref,
                "authority": "non_human",
                "capabilities": holdings,
                "can_complete_alone": all(holdings.values()),
            }
        )
    separation.append(
        {
            "identity": "human.network_governance_owner",
            "authority": "human approval assertion",
            "capabilities": {capability: False for capability in required_capabilities},
            "can_complete_alone": False,
        }
    )

    incident_ledger = Ledger("academy-lab22-forge-incident")
    author_merge = authorizer.evaluate(
        CapabilityRequest("identity.forge_author", "merge_pull_request"), context=context
    )
    incident_mission = "mission.academy.lab22.forge.incident"
    recorder.record_decision(author_merge, mission_id=incident_mission)
    missing_release = authorizer.evaluate(
        ZoneCrossingRequest(
            "identity.forge_release_agent",
            "zone.main_branch",
            "zone.release_channel",
        ),
        context=context,
    )
    recorder.record_decision(missing_release, mission_id=incident_mission)
    bypass_ledger = Ledger("academy-lab22-forge-bypass")
    if include_bypass:
        northstar.merge_pull_request(bypass_ledger, "PR-BYPASS", tests_passed=False)
    incident = {
        "author_attempts_merge": {
            "decision": _decision(author_merge),
            "counter": _counter(incident_ledger, "merge_pull_request"),
        },
        "release_without_human_approval": {
            "decision": _decision(missing_release),
            "counter": _counter(incident_ledger, "publish_release"),
        },
        "failed_tests_application_gate": {
            "decision_effect": "deny",
            "decision_code": "FORGE_TESTS_FAILED",
            "counter": _counter(incident_ledger, "merge_pull_request"),
            "nornyx_claim": "application precondition, not a Nornyx decision code",
        },
        "direct_in_process_bypass": {
            "executed": include_bypass,
            "counter": _counter(bypass_ledger, "merge_pull_request"),
            "nornyx_decisions": 0,
            "coverage": "uncontrolled cooperative-boundary bypass",
            "external_effect": False,
        },
    }

    evidence = _evidence_summary(recorder)
    checks = {
        "forge_contract_lock_verified": (
            evidence["contract_digest_bound"] and evidence["network_lock_digest_bound"]
        ),
        "distinct_author_reviewer_release": (
            {
                "identity.forge_author",
                "identity.forge_reviewer",
                "identity.forge_release_agent",
            }.issubset({step["identity"] for step in workflow})
        ),
        "delegated_tests_execute": delegation.allowed and delegated_tests.allowed,
        "independent_review_executes": ledger.completions("review_patch") == 1,
        "handoff_executes": handoff_open and ledger.completions("handoff") == 1,
        "human_owner_separate": all(
            bool(value) for key, value in authority.items() if key != "human_governance_owner"
        ),
        "no_identity_can_complete_alone": all(not row["can_complete_alone"] for row in separation),
        "human_merge_approval_validated": bool(
            merge_approval is not None and merge_approval.allowed
        ),
        "combined_release_crossing_allowed": release_crossing.allowed,
        "happy_path_inert_release": (
            ledger.completions("merge_pull_request") == 1
            and ledger.completions("publish_release") == 1
            and ledger.completions("close_release") == 1
        ),
        "author_merge_prevented": (
            not author_merge.allowed and incident_ledger.attempts("merge_pull_request") == 0
        ),
        "missing_approval_prevents_release": (
            missing_release.effect.value == "approval_required"
            and incident_ledger.attempts("publish_release") == 0
        ),
        "inert_direct_bypass_visible": (
            include_bypass
            and bypass_ledger.attempts("merge_pull_request") == 1
            and bypass_ledger.completions("merge_pull_request") == 1
        ),
        "evidence_valid": evidence["status"] == "pass",
    }
    passed = all(checks.values())
    return StructuredLabRun(
        run_id=_run_id(
            "22",
            {"approval_state": approval_state, "include_inert_bypass": include_bypass},
        ),
        module_id="22",
        legacy_lab_id="22",
        title="Forge Multi-Agent Release Network",
        status=RunStatus.COMPLETE if passed else RunStatus.FAILED,
        blocks=(
            _block(
                "lab-22-workflow",
                BlockKind.DECISION_TABLE,
                title="Forge author → reviewer → release network",
                rows=tuple(workflow),
            ),
            _block(
                "lab-22-separation",
                BlockKind.DECISION_TABLE,
                title="Maker-checker and human authority separation",
                rows=tuple(separation),
            ),
            _block(
                "lab-22-incident",
                BlockKind.LEDGER_COMPARISON,
                title="Failed release and bypass reconstruction",
                rows=tuple({"path": name, **details} for name, details in incident.items()),
            ),
            _block(
                "lab-22-boundary",
                BlockKind.BOUNDARY,
                title="Approval and enforcement boundaries",
                body=(
                    "The browser exercise builds a temporary Forge contract, generated controls, "
                    "and lock through Nornyx's public Python APIs, then loads the verified "
                    "Authorizer. CapabilityRequest checks holdings; it does not consume approval "
                    "metadata. ApprovalRequest validates an assertion but does not mutate or "
                    "unlock Authorizer state, so internal merge uses an explicit application AND "
                    "gate. External release uses the combined ZoneCrossingRequest approval path. "
                    "The human governance owner is not an agent identity. Controls remain "
                    "cooperative; the inert direct merge demonstrates the bypass."
                ),
            ),
            _block(
                "lab-22-verdict",
                BlockKind.VERDICT,
                title="Executable verdict",
                body=(
                    "The Forge workflow, negative controls, lock, and evidence checks passed."
                    if passed
                    else "A Forge workflow or assurance check failed; completion is closed."
                ),
                metadata={"passed": passed},
            ),
        ),
        results={
            "scenario_id": "lab22.forge_release_network",
            "interaction": "forge-release-network",
            "configuration": {
                "approval_state": approval_state,
                "include_inert_bypass": include_bypass,
            },
            "contract": {
                "network_id": "network.northstar_forge",
                "source": "ephemeral browser-safe fixture",
                "built_with_public_nornyx_apis": True,
                "repository_mutated": False,
                "lock_verified_before_decision": True,
            },
            "workflow": tuple(workflow),
            "delegation": _decision(delegation),
            "handoff": {
                "decision": _decision(handoff),
                "approval": _decision(merge_approval) if merge_approval else None,
                "counter": _counter(ledger, "handoff"),
            },
            "approvals": {
                "authority": authority,
                "merge": {
                    "validation": _decision(merge_approval) if merge_approval else None,
                    "composition": "application_explicit_conjunction",
                    "authorizer_state_mutated": False,
                    "runtime_event_recorded": False,
                    "evidence_boundary": (
                        "The candidate delivery governance approval is a real Authorizer decision, "
                        "but it is not mislabeled as the agentic-network authority in this stream."
                    ),
                },
                "release": {
                    "crossing": _decision(release_crossing),
                    "composition": "nornyx_zone_crossing_request",
                },
            },
            "separation_of_duties": tuple(separation),
            "incident": incident,
            "counters": tuple(
                _counter(ledger, action)
                for action in (
                    "read_repository",
                    "author_patch",
                    "run_tests",
                    "review_patch",
                    "handoff",
                    "merge_pull_request",
                    "publish_release",
                    "close_release",
                )
            ),
            "evidence": evidence,
            "checks": checks,
        },
        executable_checks=tuple(checks),
        completion_eligible=passed,
        safety_boundary=(
            "Forge contract generation and lock verification used an automatically removed "
            "temporary directory. Repository read, patch, tests, review, merge, release, and "
            "closure are deterministic ledger fixtures. No source-control command, network, "
            "credential, real merge, package publication, or repository mutation occurred."
        ),
    )


def _threat_row(
    row_id: str,
    *,
    threat: str,
    asset: str,
    mechanism: str,
    decision_effect: str,
    decision_code: str,
    attempts: int | None,
    completions: int | None,
    coverage: str,
    evidence_status: str,
    execution_kind: str,
) -> dict[str, Any]:
    if attempts is None or completions is None:
        meaning = "indeterminate_not_observed"
    elif attempts == completions == 0:
        meaning = "prevented_before_execution"
    elif attempts == completions and attempts > 0:
        meaning = "executed"
    elif attempts > completions:
        meaning = "attempted_not_completed"
    else:
        meaning = "indeterminate"
    return {
        "id": row_id,
        "threat": threat,
        "asset": asset,
        "mechanism": mechanism,
        "decision_effect": decision_effect,
        "decision_code": decision_code,
        "attempts": attempts,
        "completions": completions,
        "counter_meaning": meaning,
        "coverage": coverage,
        "evidence_status": evidence_status,
        "execution_kind": execution_kind,
    }


def _run_23(values: Mapping[str, Any]) -> StructuredLabRun:
    _only(values, {"include_direct_bypass"})
    include_direct_bypass = _boolean(
        values.get("include_direct_bypass"),
        name="include_direct_bypass",
        default=True,
    )
    authorizer = _authorizer("atlas")
    context = _evaluation_context()
    recorder = EvidenceRecorder(
        authorizer,
        context,
        producer_id="nornyx-lab.academy.threat-matrix",
    )
    mission_id = "mission.academy.lab23"
    governed = Ledger("academy-lab23-governed")

    search = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.research_assistant",
        capability="search_web",
    )
    if search.allowed:
        northstar.search_web(governed, "competitor pricing", hostile=False)
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission_id,
            actor_ref="identity.research_assistant",
            capability_ref="search_web",
        )

    denied_publish = _record_capability(
        authorizer=authorizer,
        context=context,
        recorder=recorder,
        mission_id=mission_id,
        identity="identity.research_assistant",
        capability="publish_external",
    )
    missing_approval = authorizer.evaluate(
        ZoneCrossingRequest(
            "identity.research_assistant",
            "zone.research_internal",
            "zone.public_web",
        ),
        context=context,
    )
    recorder.record_decision(missing_approval, mission_id=mission_id)

    wrong_revision_context = EvaluationContext(
        decision_at=LAB_AS_OF,
        observed_subject_revision="git:" + "0" * 40,
    )
    wrong_revision = authorizer.evaluate(
        CapabilityRequest("identity.research_assistant", "search_web"),
        context=wrong_revision_context,
    )

    bypass = Ledger("academy-lab23-direct-bypass")
    if include_direct_bypass:
        northstar.publish_external(bypass, "inert academy briefing")

    evidence = _evidence_summary(recorder)
    threat_matrix = (
        _threat_row(
            "TM-23-001",
            threat="declared low-risk capability on the cooperative application hook",
            asset="runtime decision and business-call ledger",
            mechanism="CapabilityRequest plus EvidenceRecorder before inert invocation",
            decision_effect=search.effect.value,
            decision_code=search.code.value,
            attempts=governed.attempts("search_web"),
            completions=governed.completions("search_web"),
            coverage="governed cooperative surface",
            evidence_status=evidence["status"],
            execution_kind="actual Nornyx decision and inert callable",
        ),
        _threat_row(
            "TM-23-002",
            threat="unheld publication capability",
            asset="public briefing channel",
            mechanism="lock-verified CapabilityRequest",
            decision_effect=denied_publish.effect.value,
            decision_code=denied_publish.code.value,
            attempts=governed.attempts("publish_external"),
            completions=governed.completions("publish_external"),
            coverage="governed cooperative surface",
            evidence_status=evidence["status"],
            execution_kind="actual Nornyx denial",
        ),
        _threat_row(
            "TM-23-003",
            threat="external trust-zone crossing without approval",
            asset="public briefing channel",
            mechanism="ZoneCrossingRequest with no ApprovalAssertion",
            decision_effect=missing_approval.effect.value,
            decision_code=missing_approval.code.value,
            attempts=governed.attempts("publish_external"),
            completions=governed.completions("publish_external"),
            coverage="governed combined crossing surface",
            evidence_status=evidence["status"],
            execution_kind="actual Nornyx approval-required decision",
        ),
        _threat_row(
            "TM-23-004",
            threat="stale or substituted subject revision",
            asset="contract and lock binding",
            mechanism="EvaluationContext exact-revision check",
            decision_effect=wrong_revision.effect.value,
            decision_code=wrong_revision.code.value,
            attempts=0,
            completions=0,
            coverage="governed decision boundary; not added to differently bound evidence",
            evidence_status="missing_by_design",
            execution_kind="actual Nornyx fail-closed decision",
        ),
        _threat_row(
            "TM-23-005",
            threat="direct in-process invocation bypasses the cooperative hook",
            asset="public briefing channel",
            mechanism="none; direct call to the same inert business callable",
            decision_effect="not_evaluated",
            decision_code="BYPASS_NO_DECISION",
            attempts=bypass.attempts("publish_external") if include_direct_bypass else 0,
            completions=bypass.completions("publish_external") if include_direct_bypass else 0,
            coverage=(
                "uncontrolled direct-call bypass"
                if include_direct_bypass
                else "negative control not selected"
            ),
            evidence_status="missing",
            execution_kind=(
                "actual inert callable bypass"
                if include_direct_bypass
                else "not executed by learner configuration"
            ),
        ),
        _threat_row(
            "TM-23-006",
            threat="a producer omits an event or never instruments a reachable path",
            asset="evidence completeness and coverage claim",
            mechanism="no independent observer is present in this Tier 2 exercise",
            decision_effect="indeterminate",
            decision_code="EVIDENCE_COMPLETENESS_NOT_ESTABLISHED",
            attempts=None,
            completions=None,
            coverage="indeterminate unobserved surface",
            evidence_status="indeterminate",
            execution_kind="assurance-boundary analysis, not a fabricated event",
        ),
    )

    standards_mapping = (
        {
            "reference": "NIST AI RMF 1.0 — GOVERN 1",
            "mapping_status": "educational_candidate_not_conformity",
            "mechanism": "versioned Nornyx contract, generated artifacts, and verified lock",
            "artifact": "contracts/atlas/network.nyx and nornyx.agentic_network.lock",
            "evidence": "lock-verified Authorizer load plus exact subject-revision decisions",
            "surface": "the declared Atlas contract and exercised cooperative decision hooks",
            "gap": (
                "does not establish an organization-wide AI risk-management program, ownership, "
                "or operating effectiveness"
            ),
            "owner": "AI governance lead",
            "review_cadence": "quarterly and on governed revision change",
            "certification_claim": False,
        },
        {
            "reference": "ISO/IEC 42001:2023 — clause 9.1",
            "mapping_status": "educational_candidate_not_conformity",
            "mechanism": "negative controls, counters, and bound runtime-event validation",
            "artifact": "this module's structured threat matrix and evidence summary",
            "evidence": "attempt/completion counters and Nornyx validation status",
            "surface": "this deterministic local exercise only",
            "gap": (
                "self-reported local evidence is not a production monitoring program or an "
                "independent evaluation of the management system"
            ),
            "owner": "AI assurance owner",
            "review_cadence": "monthly and after control-surface changes",
            "certification_claim": False,
        },
        {
            "reference": "ISO/IEC 27001:2022 Annex A — control 8.15 (Logging)",
            "mapping_status": "educational_candidate_not_conformity",
            "mechanism": "ordered Nornyx runtime-event stream bound to contract and lock digests",
            "artifact": "nornyx.agentic_runtime_events.v1 stream summarized in memory",
            "evidence": "event count, event-type counts, validation result, and stated limitations",
            "surface": "events supplied by this cooperative producer",
            "gap": (
                "no centralized production log store, access controls, retention proof, "
                "independent clock, or completeness attestation"
            ),
            "owner": "security operations owner",
            "review_cadence": "monthly and after logging-pipeline changes",
            "certification_claim": False,
        },
    )

    claims = (
        {
            "id": "CLAIM-23-001",
            "statement": (
                "On the exercised Atlas cooperative hook, the research assistant's unheld "
                "publish_external capability is denied before the inert callable is entered."
            ),
            "status": "supported",
            "tier": 2,
            "surface": "direct Authorizer integration exercised by TM-23-002",
            "evidence_refs": ("TM-23-002", "nornyx-evidence-summary"),
            "uncovered": (
                "direct in-process invocation",
                "other frameworks and async paths",
                "hostile code in the same process",
            ),
            "falsified_by": "a governed-ledger publish attempt greater than zero after denial",
        },
        {
            "id": "CLAIM-23-002",
            "statement": "All agent actions in this process are governed by Nornyx.",
            "status": "unsupported",
            "tier": None,
            "surface": "whole process",
            "evidence_refs": ("TM-23-005",),
            "uncovered": ("direct in-process invocation", "unwrapped execution paths"),
            "falsified_by": "TM-23-005 completes with zero Nornyx decisions",
        },
        {
            "id": "CLAIM-23-003",
            "statement": "The validated event stream proves every relevant event really occurred.",
            "status": "indeterminate",
            "tier": 2,
            "surface": "supplied runtime-event stream",
            "evidence_refs": ("nornyx-evidence-summary", "TM-23-006"),
            "uncovered": (
                "event truth",
                "events omitted by the producer",
                "unobserved execution surfaces",
            ),
            "falsified_by": (
                "independent observation disagrees with a supplied event or detects an omitted one"
            ),
        },
    )

    coverage = {
        "matrix_rows": len(threat_matrix),
        "actual_nornyx_decisions": 4,
        "actual_inert_business_paths": 2 if include_direct_bypass else 1,
        "governed_rows": sum("governed" in row["coverage"] for row in threat_matrix),
        "uncontrolled_rows": sum("uncontrolled" in row["coverage"] for row in threat_matrix),
        "indeterminate_rows": sum(
            row["decision_effect"] == "indeterminate" for row in threat_matrix
        ),
        "whole_process_coverage_claimed": False,
    }
    checks = {
        "allowed_control_executes": (
            search.allowed
            and governed.attempts("search_web") == 1
            and governed.completions("search_web") == 1
        ),
        "denied_control_prevents": (
            not denied_publish.allowed
            and governed.attempts("publish_external") == 0
            and governed.completions("publish_external") == 0
        ),
        "approval_required_prevents": (
            missing_approval.effect.value == "approval_required"
            and governed.attempts("publish_external") == 0
        ),
        "revision_binding_fails_closed": wrong_revision.code.value == "REVISION_MISMATCH",
        "direct_bypass_demonstrated": (
            include_direct_bypass
            and bypass.attempts("publish_external") == 1
            and bypass.completions("publish_external") == 1
        ),
        "indeterminate_path_registered": any(
            row["decision_effect"] == "indeterminate" for row in threat_matrix
        ),
        "evidence_valid_with_limitations": (
            evidence["status"] == "pass" and bool(evidence["limitations"])
        ),
        "mapping_is_educational_not_certification": all(
            row["mapping_status"] == "educational_candidate_not_conformity"
            and row["certification_claim"] is False
            and bool(row["gap"])
            for row in standards_mapping
        ),
        "unsupported_and_indeterminate_claims_registered": (
            {claim["status"] for claim in claims} == {"supported", "unsupported", "indeterminate"}
        ),
    }
    passed = all(checks.values())
    return StructuredLabRun(
        run_id=_run_id("23", {"include_direct_bypass": include_direct_bypass}),
        module_id="23",
        legacy_lab_id="23",
        title="Executable Threat Matrix, Standards Mapping, and Audit Claims",
        status=RunStatus.COMPLETE if passed else RunStatus.FAILED,
        blocks=(
            _block(
                "lab-23-threats",
                BlockKind.DECISION_TABLE,
                title="Threat and bypass matrix",
                rows=threat_matrix,
            ),
            _block(
                "lab-23-standards",
                BlockKind.DECISION_TABLE,
                title="Educational standards mapping",
                body=(
                    "These are reviewable interpretive mappings, not certification, legal advice, "
                    "or evidence of conformity. Every row names its surface, gap, owner, and cadence."
                ),
                rows=standards_mapping,
                metadata={"educational_only": True, "certification": False},
            ),
            _block(
                "lab-23-claims",
                BlockKind.DECISION_TABLE,
                title="Supported, unsupported, and indeterminate claim register",
                rows=claims,
            ),
            _block(
                "lab-23-boundary",
                BlockKind.BOUNDARY,
                title="Audit boundary",
                body=(
                    "Evidence validation establishes the structure, ordering, and binding of "
                    "supplied records. It does not establish event truth, completeness, producer "
                    "identity, independent enforcement, standards conformity, or certification. "
                    "The direct-call negative control proves why surface-scoped claims matter."
                ),
            ),
            _block(
                "lab-23-verdict",
                BlockKind.VERDICT,
                title="Executable verdict",
                body=(
                    "The matrix, counters, evidence, mappings, and claim boundaries passed."
                    if passed
                    else "An audit exercise check failed; completion is closed."
                ),
                metadata={"passed": passed},
            ),
        ),
        results={
            "configuration": {"include_direct_bypass": include_direct_bypass},
            "threat_matrix": threat_matrix,
            "coverage": coverage,
            "evidence": evidence,
            "standards_mapping": standards_mapping,
            "mapping_notice": {
                "educational_only": True,
                "certification": False,
                "qualified_review_required": True,
            },
            "unsupported_claim_register": claims,
            "checks": checks,
        },
        executable_checks=tuple(checks),
        completion_eligible=passed,
        safety_boundary=(
            "All decisions and counters were produced in memory against committed read-only "
            "contracts. The apparent search and publication effects are inert Northstar fixtures; "
            "no network, subprocess, repository mutation, credential, model, legal determination, "
            "or certification activity occurred."
        ),
    )


def run_advanced_module(
    module_id: str,
    inputs: Mapping[str, Any] | None = None,
) -> StructuredLabRun:
    """Execute one dedicated advanced browser module by exact legacy id."""

    if not isinstance(module_id, str):
        raise AdvancedInputError("module_id must be text")
    selected = module_id.strip()
    if selected not in ADVANCED_MODULE_IDS:
        raise AdvancedInputError(f"module_id must be one of: {', '.join(ADVANCED_MODULE_IDS)}")
    values = _inputs(inputs)
    if selected == "19":
        return _run_19(values)
    if selected == "22":
        return _run_forge_22(values)
    return _run_23(values)


__all__ = ["ADVANCED_MODULE_IDS", "AdvancedInputError", "run_advanced_module"]

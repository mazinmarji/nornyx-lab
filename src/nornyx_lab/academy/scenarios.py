"""Typed, inert scenarios used by the browser academy.

The five-minute Atlas demonstration deliberately has one plan and two execution
paths.  Both paths call the same Northstar business functions and use separate
side-effect ledgers.  The governed path changes only the pre-publication
boundary: it asks the lock-verified Nornyx authorizer about the declared trust-
zone crossing and records that decision with ``EvidenceRecorder``.

This is a cooperative, in-process demonstration.  It neither authenticates the
identity/approval claims nor provides an independently enforced boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from nornyx.agentic import (
    ApprovalAssertion,
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
    load_authorizer,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import shared_contract
from nornyx_lab.ledger import Ledger
from nornyx_lab.model import DeterministicPlanner, Planner, ToolCall

from .explain import explain_run
from .schemas import (
    ActionCounter,
    ClaimInterpretation,
    ClaimStatus,
    CounterMeaning,
    DecisionBasis,
    DecisionEffect,
    DecisionTrace,
    DemoOptions,
    EvidenceFinding,
    EvidencePackage,
    EvidenceStatus,
    PlannedAction,
    PlannerInput,
    ScenarioComparison,
    ScenarioRun,
    ScenarioVariant,
    TraceEvent,
)

SCENARIO_ID = "atlas-five-minute"
ATLAS_IDENTITY = "identity.research_assistant"
INTERNAL_ZONE = "zone.research_internal"
PUBLIC_ZONE = "zone.public_web"
PUBLICATION_ACTION = "publish_external"
PUBLICATION_RESOURCE = "public.example.com/briefings/q3-competitor"
MISSION_ID = "mission.atlas-five-minute"


class ScenarioUnavailable(RuntimeError):
    """Raised when a requested scenario mode cannot be run without a fallback."""


@lru_cache(maxsize=8)
def _load_atlas_authorizer(contract_path: str, lock_path: str):
    """Cache the immutable verified authorizer by its resolved fixture paths."""

    return load_authorizer(
        Path(contract_path),
        Path(lock_path),
        validation_as_of=LAB_AS_OF,
    )


@dataclass
class _TraceBuilder:
    events: list[TraceEvent]

    def add(
        self,
        phase: str,
        event_type: str,
        title: str,
        detail: str,
        **fields: Any,
    ) -> None:
        self.events.append(
            TraceEvent(
                sequence=len(self.events) + 1,
                phase=phase,
                event_type=event_type,
                title=title,
                detail=detail,
                fields=fields,
            )
        )


def _approval_for(state: str) -> ApprovalAssertion | None:
    """Build the exact assertion variant evaluated by the real authorizer."""

    if state == "missing":
        return None
    fields: dict[str, Any] = {
        "approval_ref": "agentic_network_authority",
        "claimed_approver_ref": "human.network_governance_owner",
        "claimed_actor_type": "human",
        "role": "network_governance_owner",
        "granted": True,
        "action_ref": PUBLICATION_ACTION,
        "subject_revision": LAB_SUBJECT_REVISION,
        "issued_at": APPROVAL_ISSUED_AT,
        "expires_at": APPROVAL_EXPIRES_AT,
        "evidence_refs": ("approval_record", "agentic_network_contract_review"),
    }
    if state == "expired":
        fields.update(
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2026-01-08T00:00:00Z",
        )
    elif state == "non_human":
        fields["claimed_actor_type"] = "ai_tool"
    elif state == "wrong_revision":
        fields["subject_revision"] = "git:" + "0" * 40
    elif state != "valid":
        raise ValueError(f"unsupported approval state: {state}")
    return ApprovalAssertion(**fields)


def _stable_run_id(options: DemoOptions, calls: tuple[ToolCall, ...]) -> str:
    payload = json.dumps(
        {
            "options": options.model_dump(mode="json"),
            "captured_plan": [
                {
                    "action": call.action,
                    "arguments": call.args,
                    "because": call.because,
                }
                for call in calls
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"atlas-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _planned_actions(plan: tuple[ToolCall, ...]) -> tuple[PlannedAction, ...]:
    return tuple(
        PlannedAction(
            index=index,
            action=call.action,
            arguments={str(key): str(value) for key, value in call.args.items()},
            rationale=call.because,
            influenced_by=tuple(
                snippet for snippet in (call.because,) if call.because.startswith("context said:")
            ),
        )
        for index, call in enumerate(plan, start=1)
    )


def _perform(ledger: Ledger, call: ToolCall, *, injection_enabled: bool) -> None:
    """Execute one inert Northstar callable and nothing outside the process."""

    if call.action == "search_web":
        northstar.search_web(
            ledger,
            call.args.get("query", "competitor pricing"),
            hostile=injection_enabled,
        )
        return
    northstar.perform(ledger, call.action, **call.args)


def _append_business_events(
    trace: _TraceBuilder,
    ledger: Ledger,
    start: int,
    *,
    action: str,
) -> None:
    for entry in ledger.entries[start:]:
        phase = "attempt" if entry.event.endswith("_attempted") else "completion"
        trace.add(
            phase,
            entry.event,
            f"{action.replace('_', ' ').title()} {phase}",
            "The inert Northstar callable was entered."
            if phase == "attempt"
            else "The inert Northstar callable finished and recorded its simulated effect.",
            ledger=ledger.name,
            ledger_sequence=entry.seq,
            **entry.fields,
        )


def _counter(ledger: Ledger, action: str, *, planned: bool) -> ActionCounter:
    attempts = ledger.attempts(action)
    completions = ledger.completions(action)
    if not planned and attempts == completions == 0:
        meaning = CounterMeaning.NOT_PLANNED
    elif attempts == completions == 0:
        meaning = CounterMeaning.PREVENTED
    elif attempts > 0 and completions == 0:
        meaning = CounterMeaning.ATTEMPTED_NOT_COMPLETED
    elif attempts > 0 and attempts == completions:
        meaning = CounterMeaning.EXECUTED
    else:
        meaning = CounterMeaning.INDETERMINATE
    return ActionCounter(
        action=action,
        attempts=attempts,
        completions=completions,
        meaning=meaning,
    )


def _diagnostic_finding(item: dict[str, Any]) -> EvidenceFinding:
    level = str(item.get("level", "warning"))
    return EvidenceFinding(
        status=EvidenceStatus.FAIL if level == "error" else EvidenceStatus.UNKNOWN,
        code=str(item.get("code", "EVIDENCE_DIAGNOSTIC")),
        message=str(item.get("message", "Evidence validation returned a diagnostic.")),
        path=str(item["path"]) if item.get("path") is not None else None,
    )


def _recorded_evidence(recorder: EvidenceRecorder) -> EvidencePackage:
    stream = recorder.stream()
    report = recorder.validate()
    raw_diagnostics = report.get("diagnostics", [])
    findings = tuple(
        _diagnostic_finding(item) for item in raw_diagnostics if isinstance(item, dict)
    )
    status_text = str(report.get("status", "unknown")).lower()
    status = {
        "pass": EvidenceStatus.PASS,
        "fail": EvidenceStatus.FAIL,
    }.get(status_text, EvidenceStatus.UNKNOWN)
    limitations = report.get("limitations", [])
    stated = "; ".join(str(item) for item in limitations) if isinstance(limitations, list) else ""
    limitation = (
        "The recorder validates construction, ordering, and binding of supplied records; "
        "it does not authenticate the producer or attest that an external effect occurred."
    )
    if stated:
        limitation += f" Validator limitation: {stated}"
    producer = stream.get("producer", {})
    producer_id = str(producer.get("id", "nornyx-lab.academy.atlas"))
    producer_type = str(producer.get("type", "framework_adapter"))
    return EvidencePackage(
        producer=producer_id,
        producer_type=producer_type,
        schema_id=str(stream.get("schema", "nornyx.agentic_runtime_events.v1")),
        events=tuple(event for event in stream.get("events", []) if isinstance(event, dict)),
        validation_status=status,
        findings=findings,
        integrity_observed=status is EvidenceStatus.PASS,
        completeness_observed=None,
        limitation=limitation,
    )


def _missing_evidence(code: str, message: str) -> EvidencePackage:
    return EvidencePackage(
        producer="none",
        producer_type="none",
        schema_id="nornyx.agentic_runtime_events.v1",
        events=(),
        validation_status=EvidenceStatus.MISSING,
        findings=(
            EvidenceFinding(
                status=EvidenceStatus.MISSING,
                code=code,
                message=message,
            ),
        ),
        integrity_observed=None,
        completeness_observed=None,
        limitation=(
            "No bound Nornyx decision-event stream is available for this path, so neither "
            "evidence integrity nor completeness can be concluded."
        ),
    )


def _basis_for(decision: Any) -> tuple[DecisionBasis, ...]:
    return tuple(
        DecisionBasis(kind=item.kind, ref=item.ref, detail=item.detail) for item in decision.basis
    )


def _declared_crossing_context(document: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    network = document.get("agentic_network", {})
    gates = network.get("network_gates", []) if isinstance(network, dict) else []
    matched = [
        gate
        for gate in gates
        if isinstance(gate, dict)
        and INTERNAL_ZONE in gate.get("source_zone_refs", [])
        and PUBLIC_ZONE in gate.get("target_zone_refs", [])
        and PUBLICATION_ACTION in gate.get("action_classes", [])
    ]
    return (
        tuple(str(gate.get("id")) for gate in matched if gate.get("id")),
        tuple(
            sorted(
                {
                    str(ref)
                    for gate in matched
                    for ref in gate.get("required_policy_refs", [])
                    if isinstance(ref, str)
                }
            )
        ),
    )


def _ungoverned_variant(
    calls: tuple[ToolCall, ...],
    *,
    injection_enabled: bool,
) -> tuple[ScenarioVariant, Ledger]:
    ledger = Ledger("atlas-ungoverned")
    trace = _TraceBuilder([])
    trace.add(
        "plan",
        "plan_reused",
        "Shared plan accepted",
        "This is the same captured planner output used by the governed variant.",
        actions=[call.action for call in calls],
    )
    for call in calls:
        start = len(ledger.entries)
        _perform(ledger, call, injection_enabled=injection_enabled)
        _append_business_events(trace, ledger, start, action=call.action)

    actions = ("search_web", "draft_briefing", PUBLICATION_ACTION)
    planned = {call.action for call in calls}
    counters = tuple(_counter(ledger, action, planned=action in planned) for action in actions)
    publication = next(item for item in counters if item.action == PUBLICATION_ACTION)
    ran = publication.attempts == 1 and publication.completions == 1
    claims = (
        ClaimInterpretation(
            claim=(
                "The inert publication callable was attempted and completed once on the "
                "ungoverned path."
            ),
            status=ClaimStatus.SUPPORTED if ran else ClaimStatus.UNSUPPORTED,
            because=(
                "The isolated side-effect ledger records one attempt and one completion."
                if ran
                else "The shared plan did not produce a completed publication in this configuration."
            ),
            evidence_refs=("ledger:atlas-ungoverned",),
            limitation="The callable is a local simulator; no real publication occurred.",
        ),
        ClaimInterpretation(
            claim="Nornyx authorized or prevented the ungoverned publication.",
            status=ClaimStatus.UNSUPPORTED,
            because="The ungoverned path never loaded or consulted a Nornyx authorizer.",
            evidence_refs=(),
            limitation="A business ledger is not governance-decision evidence.",
        ),
    )
    return (
        ScenarioVariant(
            id="ungoverned",
            title="Without governance",
            governance_enabled=False,
            decisions=(),
            counters=counters,
            trace=tuple(trace.events),
            evidence=_missing_evidence(
                "NO_GOVERNANCE_EVIDENCE",
                "The ungoverned path intentionally did not produce Nornyx decision evidence.",
            ),
            claims=claims,
        ),
        ledger,
    )


def _fallback_decision(
    options: DemoOptions,
    *,
    gate_refs: tuple[str, ...],
    policy_refs: tuple[str, ...],
) -> tuple[DecisionTrace, bool, str]:
    if not options.enforcement_enabled:
        return (
            DecisionTrace(
                requested=False,
                effect=DecisionEffect.NOT_EVALUATED,
                code="ENFORCEMENT_DISABLED",
                reason="The configured application enforcement point was disabled; Nornyx was not consulted.",
                identity=options.identity_ref,
                capability=PUBLICATION_ACTION,
                resource=PUBLICATION_RESOURCE,
                source_zone=INTERNAL_ZONE,
                target_zone=PUBLIC_ZONE,
                policy_refs=policy_refs,
                gate_refs=gate_refs,
                approval_state=options.approval_state,
                enforcement_point="disabled application pre-call boundary",
                coverage_surface="uncovered direct call",
                basis=(),
            ),
            True,
            "disabled",
        )

    fail_open = options.failure_mode == "fail_open"
    bounded = options.failure_mode == "bounded"
    code = (
        "ENFORCEMENT_FAILURE_FAIL_OPEN"
        if fail_open
        else ("ENFORCEMENT_FAILURE_BOUNDED_BLOCK" if bounded else "ENFORCEMENT_FAILURE_FAIL_CLOSED")
    )
    outcome = (
        "The application chose fail-open behavior and continued without a Nornyx decision."
        if fail_open
        else (
            "An application-defined bounded fallback blocked irreversible public publication; "
            "this is not a Nornyx policy decision."
            if bounded
            else "The application chose fail-closed behavior and stopped before the callable."
        )
    )
    return (
        DecisionTrace(
            requested=True,
            effect=DecisionEffect.ERROR,
            code=code,
            reason=outcome,
            identity=options.identity_ref,
            capability=PUBLICATION_ACTION,
            resource=PUBLICATION_RESOURCE,
            source_zone=INTERNAL_ZONE,
            target_zone=PUBLIC_ZONE,
            policy_refs=policy_refs,
            gate_refs=gate_refs,
            approval_state=options.approval_state,
            enforcement_point="application pre-call boundary (simulated unavailable authorizer)",
            coverage_surface="cooperative in-process error handling",
            basis=(
                DecisionBasis(
                    kind="application_fallback",
                    ref=options.failure_mode,
                    detail="Configured by the lab; not a Nornyx semantic.",
                ),
            ),
        ),
        fail_open,
        "failure",
    )


def _governed_variant(
    calls: tuple[ToolCall, ...],
    options: DemoOptions,
) -> tuple[ScenarioVariant, Ledger, str]:
    ledger = Ledger("atlas-governed")
    trace = _TraceBuilder([])
    trace.add(
        "plan",
        "plan_reused",
        "Shared plan accepted",
        "This is the same captured planner output used by the ungoverned variant.",
        actions=[call.action for call in calls],
    )

    publication_planned = any(call.action == PUBLICATION_ACTION for call in calls)
    authorizer = None
    load_failure: Exception | None = None
    if publication_planned and options.enforcement_enabled and not options.enforcement_failure:
        atlas = shared_contract("atlas")
        try:
            authorizer = _load_atlas_authorizer(
                str((atlas / "network.nyx").resolve()),
                str((atlas / "nornyx.agentic_network.lock").resolve()),
            )
        except Exception as exc:  # the configured failure policy handles load failure explicitly
            load_failure = exc

    if authorizer is not None:
        gate_refs, policy_refs = _declared_crossing_context(authorizer.state.document)
    else:
        gate_refs, policy_refs = ("gate.publication_review",), ("AtlasGovernance",)

    recorder: EvidenceRecorder | None = None
    recorder_failure: str | None = None
    decisions: list[DecisionTrace] = []
    fallback_kind: str | None = None

    if (
        publication_planned
        and options.enforcement_enabled
        and not options.enforcement_failure
        and authorizer
    ):
        observed_revision = options.observed_subject_revision or LAB_SUBJECT_REVISION
        eval_ctx = EvaluationContext(
            decision_at=LAB_AS_OF,
            observed_subject_revision=observed_revision,
        )
        approval = _approval_for(options.approval_state)
        capability_decision = authorizer.evaluate(
            CapabilityRequest(options.identity_ref, PUBLICATION_ACTION),
            context=eval_ctx,
        )
        crossing_decision = authorizer.evaluate(
            ZoneCrossingRequest(
                options.identity_ref,
                INTERNAL_ZONE,
                PUBLIC_ZONE,
                approval,
            ),
            context=eval_ctx,
        )
        trace.add(
            "decision",
            "nornyx_capability_decision",
            "Lock-verified capability decision",
            capability_decision.reason
            or "The identity holds the requested publication capability.",
            effect=capability_decision.effect.value,
            code=capability_decision.code.value,
            identity=options.identity_ref,
            capability=PUBLICATION_ACTION,
        )
        decisions.append(
            DecisionTrace(
                effect=capability_decision.effect.value,
                code=capability_decision.code.value,
                reason=capability_decision.reason
                or "The lock-verified authorizer allowed the requested capability.",
                identity=options.identity_ref,
                capability=PUBLICATION_ACTION,
                resource=PUBLICATION_RESOURCE,
                policy_refs=policy_refs,
                gate_refs=(),
                approval_state="not_applicable",
                enforcement_point="application pre-call capability boundary",
                coverage_surface="cooperative in-process publication path",
                basis=_basis_for(capability_decision),
            )
        )
        trace.add(
            "decision",
            "nornyx_zone_crossing_decision",
            "Lock-verified zone-crossing decision",
            crossing_decision.reason
            or "The declared crossing and supplied assertion were allowed.",
            effect=crossing_decision.effect.value,
            code=crossing_decision.code.value,
            identity=options.identity_ref,
            source_zone=INTERNAL_ZONE,
            target_zone=PUBLIC_ZONE,
            approval_state=options.approval_state,
        )
        decisions.append(
            DecisionTrace(
                effect=crossing_decision.effect.value,
                code=crossing_decision.code.value,
                reason=crossing_decision.reason
                or "The lock-verified authorizer allowed the declared crossing.",
                identity=options.identity_ref,
                capability="cross_zone_publication",
                resource=PUBLICATION_RESOURCE,
                source_zone=INTERNAL_ZONE,
                target_zone=PUBLIC_ZONE,
                policy_refs=policy_refs,
                gate_refs=gate_refs,
                approval_state=options.approval_state,
                enforcement_point="application pre-call boundary",
                coverage_surface="cooperative in-process publication path",
                basis=_basis_for(crossing_decision),
            )
        )
        try:
            recorder = EvidenceRecorder(
                authorizer,
                eval_ctx,
                producer_id="nornyx-lab.academy.atlas",
                producer_version="1.0",
                # Nornyx permits exactly three producer types: external_runtime,
                # framework_adapter, and synthetic_harness. `synthetic_harness`
                # is the honest one here — this scenario engine is a
                # deterministic teaching harness that SUPPLIES events. Calling it
                # a framework_adapter would overclaim (no framework executes this
                # path), and external_runtime would imply an independent
                # producer, which is exactly the Tier 3 claim the academy must
                # not make.
                producer_type="synthetic_harness",
            )
            recorder.record_decision(capability_decision, mission_id=MISSION_ID)
            recorder.record_decision(crossing_decision, mission_id=MISSION_ID)
        except ValueError as exc:
            # A revision mismatch is a real decision, but the recorder correctly
            # refuses to stamp it as though it were bound to the contract revision.
            recorder_failure = str(exc)
        # Approval can allow the crossing; it never grants a capability. The
        # application enforces both independent decisions before tool entry.
        publication_allowed = capability_decision.allowed and crossing_decision.allowed
    elif publication_planned:
        # A configured injection can reach this branch either because the
        # boundary was deliberately disabled, an outage was injected, or the
        # real authorizer failed to load.  All three are represented as
        # application behavior rather than forged Nornyx effects/codes.
        effective_options = options
        if load_failure is not None and not options.enforcement_failure:
            effective_options = options.model_copy(update={"enforcement_failure": True})
        fallback, publication_allowed, fallback_kind = _fallback_decision(
            effective_options,
            gate_refs=gate_refs,
            policy_refs=policy_refs,
        )
        decisions.append(fallback)
        trace.add(
            "decision",
            "application_enforcement_state",
            "No Nornyx policy decision",
            fallback.reason,
            effect=fallback.effect,
            code=fallback.code,
            authorizer_load_error=type(load_failure).__name__ if load_failure else None,
        )
    else:
        publication_allowed = False

    for call in calls:
        if call.action == PUBLICATION_ACTION and not publication_allowed:
            trace.add(
                "finding",
                "business_callable_not_entered",
                "Publication callable not entered",
                "The publication ledger remains at zero attempts and zero completions.",
                action=PUBLICATION_ACTION,
            )
            continue
        start = len(ledger.entries)
        _perform(ledger, call, injection_enabled=options.injection_enabled)
        _append_business_events(trace, ledger, start, action=call.action)

    actions = ("search_web", "draft_briefing", PUBLICATION_ACTION)
    planned = {call.action for call in calls}
    counters = tuple(_counter(ledger, action, planned=action in planned) for action in actions)
    publication = next(item for item in counters if item.action == PUBLICATION_ACTION)

    if recorder is not None:
        evidence = _recorded_evidence(recorder)
        trace.add(
            "evidence",
            "bound_decision_stream",
            "Bound decision evidence assembled",
            f"The recorder returned {len(evidence.events)} bound event(s).",
            validation_status=evidence.validation_status,
        )
    elif recorder_failure:
        evidence = _missing_evidence("EVIDENCE_BINDING_REFUSED", recorder_failure)
    elif not publication_planned:
        evidence = _missing_evidence(
            "NO_GOVERNED_ACTION_PLANNED",
            "No publication action was planned, so no publication decision was requested.",
        )
    elif fallback_kind == "disabled":
        evidence = _missing_evidence(
            "ENFORCEMENT_DISABLED",
            "The disabled path did not ask Nornyx for a decision.",
        )
    else:
        evidence = _missing_evidence(
            "AUTHORIZER_UNAVAILABLE",
            "The application fallback path has no Nornyx decision event to record.",
        )

    prevented = publication_planned and publication.attempts == publication.completions == 0
    executed = publication.attempts == publication.completions == 1
    real_decision = bool(decisions) and decisions[0].code not in {
        "ENFORCEMENT_DISABLED",
        "ENFORCEMENT_FAILURE_FAIL_OPEN",
        "ENFORCEMENT_FAILURE_FAIL_CLOSED",
        "ENFORCEMENT_FAILURE_BOUNDED_BLOCK",
    }

    if not publication_planned:
        primary_claim = ClaimInterpretation(
            claim="The governed boundary prevented a planned publication.",
            status=ClaimStatus.UNSUPPORTED,
            because="With injection disabled, the deterministic planner proposed no publication.",
            evidence_refs=("ledger:atlas-governed",),
            limitation="Zero counters mean not planned here, not prevented.",
        )
    elif prevented and real_decision:
        primary_claim = ClaimInterpretation(
            claim=(
                "On the named cooperative in-process publication path, the Nornyx decision "
                "was enforced before the inert callable was entered."
            ),
            status=ClaimStatus.SUPPORTED,
            because="A real authorizer decision precedes zero publication attempts and zero completions.",
            evidence_refs=("nornyx:decision", "ledger:atlas-governed"),
            limitation=(
                "This cooperative boundary does not cover direct/bypass paths and is not "
                "independent enforcement; identity and approval fields are caller-supplied claims."
            ),
        )
    elif prevented:
        primary_claim = ClaimInterpretation(
            claim="The application fallback stopped the inert publication callable before entry.",
            status=ClaimStatus.SUPPORTED,
            because="The governed ledger has zero attempts and zero completions.",
            evidence_refs=("ledger:atlas-governed",),
            limitation="No Nornyx policy decision was produced; this is application error handling.",
        )
    elif executed:
        primary_claim = ClaimInterpretation(
            claim="The inert publication callable was attempted and completed on the configured path.",
            status=ClaimStatus.SUPPORTED,
            because="The governed ledger records one attempt and one completion.",
            evidence_refs=("ledger:atlas-governed",),
            limitation=(
                "A valid supplied assertion can allow the declared crossing, but Nornyx does not "
                "authenticate that a human actually approved it."
                if real_decision
                else "No Nornyx decision was available on this bypass/fail-open path."
            ),
        )
    else:
        primary_claim = ClaimInterpretation(
            claim="The publication outcome is conclusively known.",
            status=ClaimStatus.INDETERMINATE,
            because="The counters do not match a supported complete outcome.",
            evidence_refs=("ledger:atlas-governed",),
            limitation="Investigate the incomplete attempt before making a prevention claim.",
        )

    claims = (
        primary_claim,
        ClaimInterpretation(
            claim="The whole Atlas runtime is governed independently of the application process.",
            status=ClaimStatus.UNSUPPORTED,
            because="Only one cooperative pre-call publication path is demonstrated.",
            evidence_refs=(),
            limitation="Direct calls, other processes, credentials, and network egress are outside coverage.",
        ),
        ClaimInterpretation(
            claim="A supplied valid approval assertion proves that the named human approved.",
            status=ClaimStatus.UNSUPPORTED,
            because="Nornyx validates assertion scope and shape but does not authenticate its producer.",
            evidence_refs=tuple(event.get("event_id", "") for event in evidence.events),
            limitation="Authentication belongs to the identity provider and approval application.",
        ),
        ClaimInterpretation(
            claim="The approval assertion granted or mutated the agent's capability membership.",
            status=ClaimStatus.UNSUPPORTED,
            because=(
                "The request evaluated here is the declared zone crossing. Approval evaluation does "
                "not alter the immutable contract or turn a generic CapabilityRequest into an unlock."
            ),
            evidence_refs=tuple(event.get("event_id", "") for event in evidence.events),
            limitation=(
                "The application must choose the authorization request that accurately represents its "
                "enforcement surface; this demo does not claim a publish_external capability grant."
            ),
        ),
    )
    return (
        ScenarioVariant(
            id="governed",
            title="With Nornyx-derived governance",
            governance_enabled=True,
            decisions=tuple(decisions),
            counters=counters,
            trace=tuple(trace.events),
            evidence=evidence,
            claims=claims,
        ),
        ledger,
        primary_claim.claim,
    )


def run_atlas_demo(
    options: DemoOptions | None = None,
    *,
    planner: Planner | None = None,
) -> ScenarioRun:
    """Run the real, inert Atlas A/B and return a schema-validated result.

    The deterministic default constructs its pinned fixture planner.  Live mode
    accepts only an already-configured in-memory planner supplied by the caller;
    this service never reads settings or secrets and never constructs a network
    client.  In both modes, the planner is called once and that captured plan is
    reused for both variants, so planner variance cannot be mistaken for a
    governance outcome inside one A/B run.
    """

    selected = options or DemoOptions()
    if selected.planner_mode == "live" and planner is None:
        raise ScenarioUnavailable(
            "Live mode requires a configured in-memory planner; the deterministic fixture is "
            "never substituted silently."
        )
    if selected.planner_mode == "deterministic" and planner is not None:
        raise ValueError("A caller-supplied planner is accepted only when planner_mode='live'.")

    context = northstar.HOSTILE_PAGE if selected.injection_enabled else northstar.CLEAN_PAGE
    task = "Research competitor pricing and write a briefing"
    selected_planner: Planner = planner if planner is not None else DeterministicPlanner()
    plan = selected_planner.plan(task, context)
    calls = tuple(plan.calls)
    deterministic = selected.planner_mode == "deterministic"
    planner_model_value = getattr(selected_planner, "model", None)
    planner_model = (
        planner_model_value if not deterministic and isinstance(planner_model_value, str) else None
    )

    ungoverned, _ = _ungoverned_variant(
        calls,
        injection_enabled=selected.injection_enabled,
    )
    governed, _, strongest = _governed_variant(calls, selected)

    if not deterministic:
        live_limitation = ClaimInterpretation(
            claim="The injected live planner will reproduce this exact plan on another run.",
            status=ClaimStatus.UNSUPPORTED,
            because=(
                "Live-model output may vary. This comparison reuses one captured plan so the two "
                "paths inside this run remain comparable."
            ),
            evidence_refs=(),
            limitation=(
                "Planner nondeterminism affects proposed actions; it does not change the real "
                "authorization request or enforcement ordering applied to the captured actions."
            ),
        )
        ungoverned = ungoverned.model_copy(update={"claims": (*ungoverned.claims, live_limitation)})
        governed = governed.model_copy(update={"claims": (*governed.claims, live_limitation)})

    comparisons = tuple(
        ScenarioComparison(
            action=left.action,
            ungoverned=left,
            governed=right,
            changed=(left.attempts, left.completions) != (right.attempts, right.completions),
            interpretation=(
                "The same planned action reached different pre-call enforcement outcomes."
                if (left.attempts, left.completions) != (right.attempts, right.completions)
                else "The measured side-effect counters are the same on both paths."
            ),
        )
        for left, right in zip(ungoverned.counters, governed.counters, strict=True)
    )

    run = ScenarioRun(
        scenario_id=SCENARIO_ID,
        run_id=_stable_run_id(selected, calls),
        title="Atlas: untrusted research content attempts public publication",
        deterministic=deterministic,
        safety_boundary=(
            "All Northstar tools are inert local callables. The publication URL is a fixed training "
            "string; no network request, credential, external repository, or business action occurs."
        ),
        planner_input=PlannerInput(
            task=task,
            context=context,
            context_origin="Northstar training web-page fixture",
            context_authority="informs_only",
            context_taint="untrusted" if selected.injection_enabled else "trusted",
            planner_kind="deterministic_fixture" if deterministic else "live_model",
            model=planner_model,
        ),
        plan=_planned_actions(calls),
        variants=(ungoverned, governed),
        comparison=comparisons,
        strongest_claim=strongest,
        residual_risk=(
            "A cooperative in-process wrapper can be disabled or bypassed, caller-supplied identities "
            "and approvals can be false, and recorder validation cannot attest real-world occurrence."
            + (
                " Live planner output may differ between runs; only the captured plan is shared "
                "within this comparison."
                if not deterministic
                else ""
            )
        ),
        restored=True,
    )
    # Derived last, from the finished run, so the explanation can never describe
    # anything the engine did not actually report.
    return run.model_copy(update={"explanation": explain_run(run)})


# Stable, descriptive aliases for API/router code and older prototypes.
run_five_minute_demo = run_atlas_demo
run_demo = run_atlas_demo


__all__ = [
    "ScenarioUnavailable",
    "run_atlas_demo",
    "run_demo",
    "run_five_minute_demo",
]

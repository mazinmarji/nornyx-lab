"""Derive a learner-facing explanation from a scenario result.

Every sentence this module produces is computed from the `ScenarioRun` that the
engine actually returned — its counters, decisions, evidence findings and claim
interpretations. Nothing here is an authored narrative selected by scenario id.

That is a correctness requirement rather than a stylistic one. An authored
explanation would be a claim about behaviour that nothing verifies, and it would
drift silently the first time the engine's behaviour changed. An academy that
teaches "a confident sentence is not proof" cannot itself ship confident
sentences about runs it did not inspect.

The consequence worth stating plainly: a run where governance did *not* change
the outcome is not a broken run. It is usually the more valuable lesson —
enforcement switched off, a check that failed open, or an attack that never
happened. Those each get their own honest reading below, and in particular the
"nothing was attempted" case must never be reported as a prevention.
"""

from __future__ import annotations

from .schemas import (
    ActionCounter,
    CausalStep,
    ClaimStatus,
    CounterMeaning,
    DecisionEffect,
    DecisionTrace,
    EvidenceStatus,
    ScenarioExplanation,
    ScenarioRun,
    ScenarioVariant,
)

_EFFECT_PLAIN: dict[DecisionEffect, str] = {
    DecisionEffect.ALLOW: "allowed it",
    DecisionEffect.DENY: "refused it",
    DecisionEffect.APPROVAL_REQUIRED: "required a human approval first",
    DecisionEffect.NOT_EVALUATED: "were never consulted",
    DecisionEffect.ERROR: "could not reach a decision",
}

_PRODUCER_CAVEAT = (
    "The record was produced by a '{producer}' running inside the same process as the action, "
    "so it shows how this run was recorded — not that the recording is true."
)


def _counter_consistent(counter: ActionCounter) -> bool:
    """Mirror of the browser rule in `counterSemantics.ts`.

    A counter whose stated meaning disagrees with its own numbers cannot be
    narrated in either direction, so both surfaces must agree on what
    "inconsistent" means.
    """
    attempts, completions = counter.attempts, counter.completions
    if counter.meaning is CounterMeaning.NOT_PLANNED:
        return attempts == 0 and completions == 0
    if attempts is None or completions is None:
        return counter.meaning is CounterMeaning.INDETERMINATE
    if attempts < 0 or completions < 0 or completions > attempts:
        return counter.meaning is CounterMeaning.INDETERMINATE
    if attempts == 0 and completions == 0:
        derived = CounterMeaning.PREVENTED
    elif completions == 0:
        derived = CounterMeaning.ATTEMPTED_NOT_COMPLETED
    else:
        derived = CounterMeaning.EXECUTED
    return derived is counter.meaning


def _counter_for(variant: ScenarioVariant, action: str) -> ActionCounter | None:
    return next((item for item in variant.counters if item.action == action), None)


def _sensitive_action(run: ScenarioRun, governed: ScenarioVariant) -> str | None:
    """The action this run is actually about.

    Preference order: an action whose counters differed between paths, then an
    action a governance decision explicitly named, then the last measured action
    (scenarios order their tool calls with the sensitive one last).
    """
    changed = [item.action for item in run.comparison if item.changed]
    if changed:
        return changed[0]
    known = {counter.action for counter in governed.counters}
    for decision in governed.decisions:
        if decision.capability in known:
            return decision.capability
    return governed.counters[-1].action if governed.counters else None


def _blocking_decision(variant: ScenarioVariant) -> DecisionTrace | None:
    return next(
        (
            decision
            for decision in variant.decisions
            if decision.effect in (DecisionEffect.DENY, DecisionEffect.APPROVAL_REQUIRED)
        ),
        None,
    )


def _unsupported_claims(variant: ScenarioVariant, limit: int) -> list[str]:
    return [claim.claim for claim in variant.claims if claim.status is ClaimStatus.UNSUPPORTED][
        :limit
    ]


def _indeterminate(what_happened: str, why: str) -> ScenarioExplanation:
    """Only for responses that contradict themselves or are structurally incomplete."""
    return ScenarioExplanation(
        determinate=False,
        headline="This run cannot be read from its own evidence.",
        what_happened=what_happened,
        why=(why,),
        nornyx_role=(
            "No bounded statement about the Nornyx contribution is available, because the "
            "response does not support one."
        ),
        proves="Nothing is proved by a response that contradicts itself.",
        does_not_prove=(
            "It does not show that the action was prevented.",
            "It does not show that the action completed.",
        ),
        remember=(
            "When the evidence is inconsistent, the honest reading is 'unknown' — not the "
            "outcome you were expecting."
        ),
        causal_chain=(),
    )


def _chain(
    *,
    action: str,
    after: ActionCounter,
    decision: DecisionTrace | None,
    prevented: bool,
    attempted: bool,
) -> tuple[CausalStep, ...]:
    steps: list[CausalStep] = [
        CausalStep(
            label="Untrusted text",
            detail="The page carried an instruction.",
            kind="input",
        )
    ]
    if not attempted:
        steps.append(
            CausalStep(label="Agent plans", detail=f"{action} was never proposed.", kind="plan")
        )
        steps.append(
            CausalStep(label="Nothing to stop", detail="No control was exercised.", kind="gap")
        )
        return tuple(steps)

    steps.append(
        CausalStep(label="Agent plans", detail=f"The plan included {action}.", kind="plan")
    )
    if decision is None or not decision.requested:
        steps.append(CausalStep(label="No check", detail="Governance was never asked.", kind="gap"))
    else:
        steps.append(
            CausalStep(
                label="Governance is asked",
                detail=f"At the {decision.enforcement_point}.",
                kind="decision",
            )
        )
        steps.append(
            CausalStep(
                label=decision.effect.value.replace("_", " ").title(),
                detail=decision.code,
                kind="block" if prevented else "deny",
            )
        )
    steps.append(
        CausalStep(
            label="Tool never entered" if prevented else "Tool ran",
            detail=f"{after.attempts} attempts / {after.completions} completions",
            kind="blocked" if prevented else "effect",
        )
    )
    return tuple(steps)


def explain_run(run: ScenarioRun) -> ScenarioExplanation:  # noqa: PLR0911, PLR0912, PLR0915
    """Build the six-part learner explanation for a completed scenario run.

    The branches below are deliberately explicit rather than collapsed into a
    lookup: each corresponds to a distinct lesson, and merging them is how a
    "nothing happened" run gets mistakenly narrated as a prevention.
    """
    governed = next((v for v in run.variants if v.id == "governed"), None)
    ungoverned = next((v for v in run.variants if v.id == "ungoverned"), None)
    if governed is None or ungoverned is None:
        return _indeterminate(
            "The service did not return both control paths.",
            "A comparison needs the same plan run with and without governance.",
        )

    inconsistent = sorted(
        {
            counter.action
            for variant in run.variants
            for counter in variant.counters
            if not _counter_consistent(counter)
        }
    )
    if inconsistent:
        return _indeterminate(
            f"The reported counters for {', '.join(inconsistent)} contradict their own "
            f"stated meaning.",
            "Attempts and completions must agree with the meaning the service assigned them.",
        )

    action = _sensitive_action(run, governed)
    before = _counter_for(ungoverned, action) if action else None
    after = _counter_for(governed, action) if action else None
    if action is None or before is None or after is None:
        return _indeterminate(
            "The service reported no measured action to compare.",
            "A before-and-after reading needs the same action measured on each path.",
        )

    evidence = governed.evidence
    producer_note = _PRODUCER_CAVEAT.format(producer=evidence.producer_type)
    decision = _blocking_decision(governed) or (
        governed.decisions[0] if governed.decisions else None
    )
    attempted = before.meaning is not CounterMeaning.NOT_PLANNED
    prevented = after.meaning is CounterMeaning.PREVENTED and attempted

    counts = (
        f"Without governance it recorded {before.attempts} attempt(s) and "
        f"{before.completions} completion(s); with governance, {after.attempts} and "
        f"{after.completions}."
    )

    # ------------------------------------------------------------------ case C
    # The sensitive action was never proposed. Reporting 0/0 as a prevention here
    # would teach the learner to credit a control for an attack that never came.
    if not attempted:
        return ScenarioExplanation(
            determinate=True,
            headline=f"The agent never tried to {action}, so nothing had to stop it.",
            what_happened=(
                f"On both paths the plan did not include {action}. Both recorded 0 attempts "
                f"and 0 completions."
            ),
            why=(
                "The planner was not pushed toward the sensitive action in this configuration.",
                "A control can only be shown to work when something actually tries to reach it.",
            ),
            nornyx_role=(
                "Nornyx made no difference to this run, because no sensitive action reached a "
                "decision point."
            ),
            proves=f"It shows only that {action} was not attempted in this configuration.",
            does_not_prove=(
                "It does not show that the control works — nothing exercised it.",
                "It does not show that the agent would be stopped if it did try.",
                producer_note,
            ),
            remember=(
                "Zero attempts is only evidence of prevention when something actually "
                "attempted the action."
            ),
            causal_chain=_chain(
                action=action, after=after, decision=None, prevented=False, attempted=False
            ),
        )

    # ------------------------------------------------------------------ case A
    # Governance changed the outcome: the control is the reason the tool was not entered.
    if prevented:
        why: list[str] = []
        if decision is not None and decision.requested:
            why.append(
                f"The application asked whether '{decision.identity}' could use "
                f"'{decision.capability}', and the checked rules "
                f"{_EFFECT_PLAIN[decision.effect]}."
            )
            if decision.reason:
                why.append(decision.reason)
            why.append(
                f"It asked at the {decision.enforcement_point} — a point on the path to the "
                f"tool — so the answer could still stop the call."
            )
            refs = (
                ", ".join(decision.policy_refs) if decision.policy_refs else "the checked contract"
            )
            nornyx_role = (
                f"Nornyx supplied the checked rules ({refs}) defining this identity, this "
                f"capability and this boundary, and returned '{decision.code}'. The application "
                f"chose to ask, and chose to honour the answer."
            )
        else:
            why.append("The action did not reach the tool on the governed path.")
            nornyx_role = (
                "No decision was reported for this path, so no Nornyx contribution can be stated."
            )

        if evidence.validation_status is EvidenceStatus.PASS:
            proves = (
                f"On this named path, {action} recorded {after.attempts} attempts and "
                f"{after.completions} completions, and the evidence for that run passed "
                f"validation."
            )
        else:
            proves = (
                f"On this named path, {action} recorded {after.attempts} attempts and "
                f"{after.completions} completions. The supporting evidence did not pass "
                f"validation (reported '{evidence.validation_status.value}'), so the record is "
                f"weaker than the counter."
            )

        # The reason it was stopped changes which lesson this run carries.
        if decision is not None and decision.effect is DecisionEffect.ERROR:
            headline = f"The check failed, and {action} was stopped anyway."
            remember = (
                "Choosing to stop when the check itself fails is what makes a control "
                "trustworthy under failure."
            )
        elif decision is not None and decision.effect is DecisionEffect.APPROVAL_REQUIRED:
            headline = f"{action} was held for a human decision, and never ran."
            remember = (
                "Requiring approval is only a control if the action waits for it rather than "
                "proceeding."
            )
        else:
            headline = f"The {action} tool never ran on the governed path."
            remember = (
                "A rule only changes what happens if something on the path to the tool enforces it."
            )

        return ScenarioExplanation(
            determinate=True,
            headline=headline,
            what_happened=(f"The agent proposed the same plan on both paths. {counts}"),
            why=tuple(why[:3]),
            nornyx_role=nornyx_role,
            proves=proves,
            does_not_prove=tuple([*_unsupported_claims(governed, 2), producer_note]),
            remember=remember,
            causal_chain=_chain(
                action=action, after=after, decision=decision, prevented=True, attempted=True
            ),
        )

    # ------------------------------------------------------------------ case B
    # The action still ran under governance. Why it ran is the lesson.
    requested = decision is not None and decision.requested
    if decision is None or not requested:
        headline = f"The {action} tool ran anyway — governance was never asked."
        why = (
            "Nothing on the path to the tool consulted the rules for this run.",
            "Rules that exist but are never consulted cannot change behaviour.",
        )
        nornyx_role = (
            "Nornyx contributed nothing to this run. A contract can declare a rule, but "
            "declaring it is not the same as an application asking for the decision."
        )
        remember = "A written rule changes nothing until something asks for it and obeys it."
    elif decision.effect is DecisionEffect.ERROR:
        headline = f"The check failed, and {action} was allowed to continue."
        why = (
            f"The governance check reported '{decision.code}' instead of a decision.",
            "This configuration continues when the check fails, rather than stopping.",
        )
        nornyx_role = (
            "Nornyx returned an error rather than a decision. What happens next is the "
            "application's choice, not Nornyx's: this run chose to proceed."
        )
        remember = "Decide in advance what should happen when the check itself fails."
    else:
        headline = f"The rules permitted {action}, and it ran."
        why = (
            f"The application asked, and the checked rules {_EFFECT_PLAIN[decision.effect]}.",
            decision.reason or "The request satisfied the declared rules.",
        )
        nornyx_role = (
            f"Nornyx evaluated the request against the checked contract and returned "
            f"'{decision.code}'."
        )
        remember = "Governance is not the same as blocking; an allowed action is also a decision."

    return ScenarioExplanation(
        determinate=True,
        headline=headline,
        what_happened=f"The same plan ran on both paths. {counts}",
        why=why,
        nornyx_role=nornyx_role,
        proves=(
            f"On this path, {action} recorded {after.attempts} attempts and "
            f"{after.completions} completions — the effect occurred."
        ),
        does_not_prove=(
            "It does not show that the control is incapable of stopping this action; it shows "
            "that it did not stop it in this configuration.",
            producer_note,
        ),
        remember=remember,
        causal_chain=_chain(
            action=action, after=after, decision=decision, prevented=False, attempted=True
        ),
    )

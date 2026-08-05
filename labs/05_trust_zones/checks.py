"""Concept checks for Lab 05."""

from __future__ import annotations

from nornyx.agentic import DataShareRequest, EvaluationContext, ZoneCrossingRequest

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger
from nornyx_lab.model import DeterministicPlanner

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"
INTERNAL = "zone.research_internal"
PUBLIC = "zone.public_web"


def _az():
    return authorizer_for(ATLAS)


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def test_the_egress_crossing_requires_a_human_approval():
    decision = _az().evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=_ctx())
    assert decision.effect.value == "approval_required"
    assert decision.code.value == "CROSSING_APPROVAL_REQUIRED"


def test_governance_changes_the_outcome_without_changing_the_plan():
    """The decisive test: identical plans, different effects."""
    az, ctx = _az(), _ctx()
    planner = DeterministicPlanner()

    ungoverned, governed = Ledger("ungoverned"), Ledger("governed")
    page = northstar.search_web(ungoverned, "competitor pricing", hostile=True)
    northstar.search_web(governed, "competitor pricing", hostile=True)
    plan = planner.plan("Write a briefing on the competitor", page)

    for call in plan.calls:
        if call.action == "search_web":
            continue
        northstar.perform(ungoverned, call.action, **call.args)
        if call.action in {"publish_external", "external_share"}:
            if az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=ctx).allowed:
                northstar.perform(governed, call.action, **call.args)
        else:
            northstar.perform(governed, call.action, **call.args)

    assert "publish_external" in plan.actions, "the planner was fooled in both runs"
    assert ungoverned.completions("publish_external") == 1
    assert governed.completions("publish_external") == 0
    assert governed.attempts("publish_external") == 0, "prevented, not merely failed"


def test_a_never_share_category_is_refused_distinctly():
    """Not the same refusal as 'this zone does not carry that'."""
    az, ctx = _az(), _ctx()
    sensitive = az.evaluate(
        DataShareRequest(ID, ID, ("credentials",), INTERNAL, PUBLIC), context=ctx
    )
    not_allowed = az.evaluate(
        DataShareRequest(ID, ID, ("briefing_draft",), INTERNAL, PUBLIC), context=ctx
    )

    assert sensitive.code.value == "SENSITIVE_SHARING"
    assert not_allowed.code.value == "SHARE_NOT_ALLOWED"
    assert sensitive.code.value != not_allowed.code.value


def test_an_allowlisted_category_does_cross():
    """A boundary that refuses everything teaches nothing about boundaries."""
    decision = _az().evaluate(
        DataShareRequest(ID, ID, ("evidence_digest",), INTERNAL, PUBLIC), context=_ctx()
    )
    assert decision.allowed


def test_the_contract_declares_a_non_empty_never_share_set():
    text = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    assert "never_share: [secrets, credentials, tokens, private_memory]" in text


def test_authority_is_narrower_than_inclusion():
    """Relevance is not authority: many files are readable, one decides."""
    text = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    assert "include: [README.md, briefings/**/*.md]" in text
    assert "authority: [network.nyx]" in text

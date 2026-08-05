"""Concept checks for Lab 02."""

from __future__ import annotations

import hashlib
import json

from nornyx.agentic import CapabilityRequest, EvaluationContext, ZoneCrossingRequest

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger

ATLAS = shared_contract("atlas")
IDENTITY = "identity.research_assistant"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def test_declaration_alone_grants_nothing():
    """publish_external is DECLARED in the contract but held by no identity."""
    text = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    assert "name: publish_external" in text

    az = authorizer_for(ATLAS)
    decision = az.evaluate(CapabilityRequest(IDENTITY, "publish_external"), context=_ctx())
    assert not decision.allowed
    assert decision.code.value == "CAPABILITY_DENIED", (
        "declared-but-not-held must deny as DENIED, not as UNKNOWN — "
        "the contract knows the capability, this identity just does not hold it"
    )


def test_an_undeclared_capability_is_a_different_denial():
    """Default-deny distinguishes 'not yours' from 'no such thing'."""
    az = authorizer_for(ATLAS)
    decision = az.evaluate(CapabilityRequest(IDENTITY, "launch_missiles"), context=_ctx())
    assert decision.code.value == "CAPABILITY_UNKNOWN"


def test_a_correct_decision_does_not_constrain_an_unwired_action_path():
    """Layer 2 without layer 3 is the single most common governance failure."""
    az = authorizer_for(ATLAS)
    decision = az.evaluate(
        ZoneCrossingRequest(IDENTITY, "zone.research_internal", "zone.public_web"),
        context=_ctx(),
    )
    assert not decision.allowed

    rogue = Ledger("ignores decision")
    northstar.publish_external(rogue, "briefing")  # nobody consulted the decision

    assert rogue.completions("publish_external") == 1, (
        "the decision was correct and the action still happened — because nothing "
        "on the path from intent to effect applied it"
    )


def test_integrity_survives_truncation_but_completeness_does_not():
    """A signature moves two dimensions and leaves the third untouched."""
    events = [{"seq": 1, "type": "capability_requested"}, {"seq": 2, "type": "capability_denied"}]

    def digest(items):
        return hashlib.sha256(
            json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    full = digest(events)
    truncated = digest(events[:1])

    assert full != truncated
    # Both are internally consistent: each digest correctly describes its own
    # content. A verifier given only the truncated pair sees nothing wrong.
    assert truncated == digest(events[:1])


def test_fail_open_and_fail_closed_differ_under_one_identical_fault():
    def broken():
        raise RuntimeError("policy service unreachable")

    fail_open = Ledger("fail-open")
    try:
        broken()
    except RuntimeError:
        northstar.publish_external(fail_open, "briefing")

    fail_closed = Ledger("fail-closed")
    try:
        broken()
    except RuntimeError:
        fail_closed.decision("EVALUATION_UNAVAILABLE", "deny")

    assert fail_open.completions("publish_external") == 1
    assert fail_closed.completions("publish_external") == 0
    assert fail_closed.codes() == ["EVALUATION_UNAVAILABLE"]


def test_the_authorizer_itself_fails_closed_on_a_bad_load():
    """The assured construction path refuses rather than degrading (Ch. 19)."""
    from nornyx.agentic import AuthorizerLoadError, load_authorizer

    try:
        load_authorizer(
            ATLAS / "network.nyx",
            ATLAS / "does-not-exist.lock",
            validation_as_of=LAB_AS_OF,
        )
    except AuthorizerLoadError as exc:
        assert exc.code.value in {"LOCK_INVALID", "LOCK_STALE"}
    else:
        raise AssertionError("loading with a missing lock must fail, not warn")

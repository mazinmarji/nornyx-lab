"""Concept checks for Lab 16."""

from __future__ import annotations

from nornyx.agentic import (
    SPI_VERSION,
    AuthorizerLoadError,
    CapabilityRequest,
    EvaluationContext,
    ZoneCrossingRequest,
    load_authorizer,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract

ATLAS = shared_contract("atlas")
LEDGER = shared_contract("ledger")
ID = "identity.research_assistant"


def _ctx(revision: str = LAB_SUBJECT_REVISION):
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=revision)


def test_one_interpretation_two_loads_agree():
    """The property that makes injection safe."""
    a, b = authorizer_for(ATLAS), authorizer_for(ATLAS)
    for request in (
        CapabilityRequest(ID, "search_web"),
        CapabilityRequest(ID, "publish_external"),
        ZoneCrossingRequest(ID, "zone.research_internal", "zone.public_web"),
    ):
        assert a.evaluate(request, context=_ctx()).code == b.evaluate(request, context=_ctx()).code


def test_a_missing_lock_fails_closed():
    try:
        load_authorizer(ATLAS / "network.nyx", ATLAS / "nope.lock", validation_as_of=LAB_AS_OF)
    except AuthorizerLoadError as exc:
        assert exc.code.value in {"LOCK_INVALID", "LOCK_STALE"}
    else:
        raise AssertionError("must not construct an authorizer without a lock")


def test_a_valid_lock_for_a_different_contract_is_rejected():
    """Parsing is not verification."""
    try:
        load_authorizer(
            ATLAS / "network.nyx",
            LEDGER / "nornyx.agentic_network.lock",
            validation_as_of=LAB_AS_OF,
        )
    except AuthorizerLoadError as exc:
        assert exc.code.value in {"LOCK_STALE", "LOCK_INVALID"}
    else:
        raise AssertionError("a lock from another contract must not verify")


def test_state_is_a_detached_copy():
    az = authorizer_for(ATLAS)
    view = az.state.document
    original = view["project"]["name"]

    view["project"] = {"name": "Hijacked"}
    view.setdefault("capabilities", []).append({"name": "do_anything"})

    assert az.state.document["project"]["name"] == original
    assert authorizer_for(ATLAS).state.document["project"]["name"] == original


def test_mutating_state_cannot_change_a_decision():
    az = authorizer_for(ATLAS)
    before = az.evaluate(CapabilityRequest(ID, "publish_external"), context=_ctx())

    view = az.state.document
    for capability in view.get("capabilities", []):
        if isinstance(capability, dict):
            capability["risk"] = "low"

    after = az.evaluate(CapabilityRequest(ID, "publish_external"), context=_ctx())
    assert before.code == after.code


def test_a_mismatched_observed_revision_denies_everything():
    """Deployment skew becomes a refusal, not a silent mis-authorization."""
    az = authorizer_for(ATLAS)
    allowed = az.evaluate(CapabilityRequest(ID, "search_web"), context=_ctx())
    assert allowed.allowed

    skewed = az.evaluate(CapabilityRequest(ID, "search_web"), context=_ctx("git:" + "0" * 40))
    assert not skewed.allowed
    assert skewed.code.value == "REVISION_MISMATCH"


def test_the_spi_publishes_its_version():
    """A consumer must be able to state which interpretation it built against."""
    assert SPI_VERSION
    assert isinstance(SPI_VERSION, str)


def test_approval_required_comes_only_from_a_gate():
    az = authorizer_for(ATLAS)
    gated = az.evaluate(
        ZoneCrossingRequest(ID, "zone.research_internal", "zone.public_web"), context=_ctx()
    )
    assert gated.effect.value == "approval_required"

    # An error condition is a denial, never approval_required.
    malformed = az.evaluate(CapabilityRequest("identity.nobody", "search_web"), context=_ctx())
    assert malformed.effect.value == "deny"

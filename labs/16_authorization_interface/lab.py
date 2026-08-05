"""Lab 16 — The authorization interface.

Why the SPI gives you exactly one way to build an Authorizer, and refuses to
hand you a mutable view of anything.
"""

from __future__ import annotations

from nornyx.agentic import (
    AuthorizerLoadError,
    CapabilityRequest,
    EvaluationContext,
    load_authorizer,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"


def run(ctx: LabContext) -> None:
    ctx.section("The split-brain hazard")

    ctx.say(
        """
Suppose two components each read the contract and compose it themselves: the
adapter that wraps tools, and a reporting job that builds the audit package.

Now they can disagree. Not because either is buggy — because composition depends
on module versions, resolution order, and the instant of evaluation, and nothing
forces two independent readers to agree on all three.

The result is the worst kind of incident: the adapter denies, the report says
allowed, and **both are internally consistent**. There is no log line to find,
because neither component did anything wrong.

This is an **interface** problem, not a caching problem. Caching the wrong
composition faster does not help. The fix is that there must be exactly one
interpretation, constructed once and injected everywhere.
"""
    )

    ctx.code(
        """# the hazard
adapter_authz  = build_my_own_authorizer(contract)     # interpretation A
reporting_authz= build_my_own_authorizer(contract)     # interpretation B

# the interface
authorizer = load_authorizer(contract, lock, validation_as_of=AS_OF)
governed_tool = make_governed_tool(..., authorizer=authorizer, recorder=recorder)
report        = build_report(authorizer=authorizer)     # the SAME object""",
        caption="one interpretation, injected — never re-derived",
    )

    # ------------------------------------------------------ assured path
    ctx.section("The assured construction path")

    ctx.say(
        """
`load_authorizer` is not a convenience wrapper. It is the only path that runs
every stage, in order, and fails closed at the first one that objects:

1. resolve the profile registry for this contract
2. parse the document
3. run the structural checker
4. compose governance from profile + modules
5. evaluate governance rules **as of** the supplied instant
6. load the agentic-network lock
7. verify the lock against the contract and composition

A plain `Authorizer(document, composition, lock)` constructor exists in the
module, and it deliberately carries **no assurance at all** — it will happily
build an engine from a document that never passed step 3. That is not an
oversight; it is why the assured path is a separate, named function.
"""
    )

    ctx.say("Each stage failure maps deterministically into a frozen taxonomy:")
    rows = []
    for label, contract_name, lock_name in [
        ("missing lock", "network.nyx", "does-not-exist.lock"),
        ("lock from another contract", "network.nyx", None),
    ]:
        lock_path = (
            ATLAS / lock_name
            if lock_name
            else shared_contract("ledger") / "nornyx.agentic_network.lock"
        )
        try:
            load_authorizer(ATLAS / contract_name, lock_path, validation_as_of=LAB_AS_OF)
            rows.append((label, "allow", "loaded — unexpected"))
        except AuthorizerLoadError as exc:
            rows.append((label, "deny", exc.code.value))
    ctx.decisions(rows, "the load taxonomy, fail-closed")
    ctx.record("load_codes", [r[2] for r in rows])

    ctx.say(
        "Note the second row: a **valid** lock, for a **different** contract. It "
        "parses perfectly and is rejected anyway, because verification is against "
        "*this* contract and *this* composition."
    )

    # ---------------------------------------------------------- frozen state
    ctx.section("Frozen, detached views")

    az = authorizer_for(ATLAS)
    document = az.state.document
    ctx.say(
        "`Authorizer.state` exposes the loaded document, composition, and lock "
        "payload. Try to change one:"
    )

    before = document["project"]["name"]
    document["project"] = {"name": "Hijacked"}
    after = authorizer_for(ATLAS).state.document["project"]["name"]

    ctx.code(
        f"""before mutation      : {before}
after mutating a view: {after}
the authorizer's own : {az.state.document["project"]["name"]}""",
        "text",
        caption="mutating a handed-out view changes nothing",
    )
    ctx.record("state_immutable", after == before)

    ctx.concept(
        "what you may and may not conclude",
        """
The view you get is a **detached copy**. You may read it, serialise it, diff it,
and put it in a report.

You may **not** conclude that mutating it changed policy — it did not — and you
may not rely on identity between two views. This closes destroyer #3 from Lab
06: an engine that handed out live internal state would let decisions depend on
whatever a consumer did to that state earlier in the process.
""",
    )

    # --------------------------------------------------- three outcomes
    ctx.section("Three outcomes, and the one condition that produces the third")

    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    from nornyx.agentic import ZoneCrossingRequest

    rows = []
    for label, request in [
        ("held capability", CapabilityRequest(ID, "search_web")),
        ("capability not held", CapabilityRequest(ID, "publish_external")),
        (
            "crossing a gated boundary",
            ZoneCrossingRequest(ID, "zone.research_internal", "zone.public_web"),
        ),
    ]:
        d = az.evaluate(request, context=eval_ctx)
        rows.append((label, d.effect.value, d.code.value))
    ctx.decisions(rows)

    ctx.say(
        "`approval_required` is produced by exactly one condition: **a governing "
        "gate demands an approval that the request did not carry.** Not by "
        "uncertainty, not by a missing field, not by an error — those are denials."
    )

    # ---------------------------------------------------- revision binding
    ctx.section("The context must match, exactly")

    wrong_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision="git:" + "0" * 40
    )
    mismatch = az.evaluate(CapabilityRequest(ID, "search_web"), context=wrong_ctx)
    ctx.decisions(
        [("a request about a different revision", mismatch.effect.value, mismatch.code.value)],
        "observed_subject_revision is mandatory and exact",
    )
    ctx.record("revision_mismatch_code", mismatch.code.value)

    ctx.say(
        "The runtime must state which revision it believes it is running. If that "
        "disagrees with the contract, every decision is a denial — including ones "
        "that would otherwise be allowed. Deployment skew becomes a refusal rather "
        "than a silent mis-authorization."
    )

    ctx.boundary(
        """
**The interface's honesty, stated as what it will not do.**

It will not authenticate the agent, authenticate the approver, execute a tool,
observe the runtime, or assert that any event is true. It will not accept a
decision event minted by a caller.

An SPI version is published (`SPI_VERSION`) precisely so that a consumer can
state which interpretation they built against. A compatibility facade that
quietly accepted several versions would violate the single-interpretation
principle this whole lab is about.
"""
    )

    ctx.tryit(
        """
1. Load two authorizers from the same contract and evaluate the same request on
   both. Assert the codes are equal. Now do it after mutating one's `state`.
2. Find a place in your own system where two components each parse the same
   policy file. What would it take to make one of them the only reader?
"""
    )

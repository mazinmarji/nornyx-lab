"""Lab 10 — Evidence is not logging.

You already have logs. This lab shows what they are missing, by building the
same record with the binding fields attached and validating it.
"""

from __future__ import annotations

import json

from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
)

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

ID = "identity.research_assistant"
INTERNAL, PUBLIC = "zone.research_internal", "zone.public_web"


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------- the log
    ctx.section("What your logs say about a denied action")

    ctx.code(
        """logger.info("denied publish for %s", agent.role)
# 2026-06-01 12:00:00 INFO  denied publish for Research Assistant""",
        caption="a perfectly reasonable log line",
    )

    ctx.say(
        """
Ask an auditor's questions of that line:

- *Denied under which policy?* Unknown — the log does not name a contract.
- *Which revision of it?* Unknown.
- *Which agent, exactly?* A display string that two agents could share.
- *Is this all the events?* Unknown — logs have no notion of a complete stream.
- *Could someone have edited it?* Yes, and nothing would show.

The line is not wrong. It was written for an on-call engineer at 3am, and for
that reader it is fine. It simply was not built to bear weight.
"""
    )

    ctx.say(
        """
| | logs | telemetry | evidence |
|---|---|---|---|
| **audience** | an engineer debugging | a dashboard | a reviewer, later, adversarially |
| **binding** | none | none | contract, lock, revision, actor |
| **retention** | days | weeks, aggregated | as long as the claim must stand |
| **completeness** | best effort | sampled | a defined stream with ordering rules |
| **admissible for** | diagnosis | trends | a governance claim |

Telemetry is sampled *by design* — and a sampled control record is not a control
record. That is not a tuning problem; it is a category difference.
"""
    )

    # -------------------------------------------------------- the recorder
    ctx.section("The same events, bound")

    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.atlas")
    mission = "mission.q3-briefing"

    d1 = az.evaluate(CapabilityRequest(ID, "search_web"), context=eval_ctx)
    recorder.record_decision(d1, mission_id=mission)

    ledger = ctx.ledger("governed")
    if d1.allowed:
        northstar.search_web(ledger, "competitor pricing", hostile=True)
        # A post-action OBSERVATION. The engine cannot know this happened; the
        # adapter asserts it. Note which side of the boundary that puts it on.
        recorder.record_observation(
            "tool_invoked", mission_id=mission, actor_ref=ID, capability_ref="search_web"
        )

    d2 = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=eval_ctx)
    recorder.record_decision(d2, mission_id=mission)

    stream = recorder.stream()
    first = stream["events"][0]
    ctx.code(json.dumps(first, indent=2), "json", caption="one event, with its bindings")

    ctx.concept(
        "the binding fields, and the mismatch each one detects",
        """
| field | detects |
|---|---|
| `contract_digest` | this event was produced under a *different contract* than the one you are auditing |
| `network_lock_digest` | the generated artifacts differed from the ones locked |
| `subject_revision` | the event is about a different revision of the subject |
| `network_id` | the event belongs to a different network entirely |
| `mission_id` + `sequence` | a gap or a reordering within one mission |
| `producer` | which component asserted this, and at what version |

Remove any one and a specific class of mismatch becomes undetectable. That is
the test for whether a field belongs in an evidence record: *what does its
absence let through?*
""",
    )

    # -------------------------------------------------------- two phases
    ctx.section("Decision intents and observations are different things")

    kinds: dict[str, list[str]] = {"decision": [], "observation": []}
    for event in stream["events"]:
        bucket = (
            "observation"
            if event["event_type"]
            in {"tool_invoked", "tool_completed", "data_shared", "handoff_initiated"}
            else "decision"
        )
        kinds[bucket].append(event["event_type"])

    ctx.say(
        f"""
- **Decision-phase events** (`{", ".join(kinds["decision"])}`) originate inside
  `evaluate()`. The engine knows they are true because it produced them.
- **Observations** (`{", ".join(kinds["observation"]) or "none in this run"}`)
  are asserted afterwards by the adapter. The engine records their *shape* and
  *binding*; it has no way to know whether the tool really ran.

An engine that let a caller mint `capability_allowed` directly would be a
rubber stamp. Nornyx does not: decision events can only come from a decision.
"""
    )

    # --------------------------------------------------------- validation
    ctx.section("Validate the stream — and read what the report refuses to claim")

    report = recorder.validate()
    ctx.code(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "schema",
                    "status",
                    "event_count",
                    "mission_count",
                    "counts_by_type",
                    "diagnostics",
                )
                if k in report
            },
            indent=2,
        ),
        "json",
        caption="the validation report",
    )
    ctx.record("validation_status", report["status"])
    ctx.record("event_count", report["event_count"])

    limitations = report.get("limitations", [])
    ctx.boundary(
        "**The validator states its own boundary.** Verbatim from the report:\n\n"
        + "\n".join(f"- {item}" for item in limitations)
        + "\n\nA `status: pass` here means *these supplied records are internally "
        "consistent and correctly bound*. It does not mean the events happened."
    )

    # ------------------------------------------------------- minimization
    ctx.section("Complete evidence versus data minimization")

    ctx.say(
        """
These pull against each other and the tension is real, not a failure of design.

An evidence record must be specific enough to reconstruct a decision, and
retained long enough to defend it. The same record must not become a long-lived
copy of customer data in a system built for auditors rather than for privacy
review.

The workable resolution is to bind **references and digests**, not payloads:
record `case_ref` and a digest of the payload, never the payload. The digest
still detects tampering; the reference still supports reconstruction; the
personal data stays in the system that is actually governed for it.
"""
    )
    ctx.code(
        """# don't
recorder.record_observation("tool_invoked", mission_id=m,
                            customer_email="ana@example.com", ...)

# do
recorder.record_observation("tool_invoked", mission_id=m,
                            case_ref="CASE-1041",
                            payload_digest="sha256:9f2b…")""",
        caption="bind the reference, not the person",
    )

    ctx.tryit(
        """
Write the evidence contract for one governed action in your own system. Three
columns: **what is recorded**, **what each record binds to**, **how conformance
is validated**.

Then answer the question that decides everything else: *who produces it, and
what would it take for that producer to be wrong?*
"""
    )

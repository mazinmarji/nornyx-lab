"""Lab 20 — Conformance, external enforcement, and the supply chain."""

from __future__ import annotations

import json
import shutil

from nornyx_lab.contract import nornyx, run_python, shared_contract
from nornyx_lab.engine import LabContext


def run(ctx: LabContext) -> None:
    # ------------------------------------------------------------ two words
    ctx.section("Two things called conformance")

    ctx.say(
        """
| | runtime adapter conformance | static adapter conformance |
|---|---|---|
| what it is | an executable suite that drives a real framework and asserts on outcomes | a generated report about what a *contract* declares |
| what it proves | this adapter behaves as its coverage inventory claims | these declarations are internally consistent |
| what it cannot prove | that your deployment uses the adapter | anything at all about runtime |

The overclaim each enables, if you confuse them: a green **static** report read
as "our integration is tested", or a green **runtime** suite read as "our
contract is correct". They are unrelated evidence about unrelated things.
"""
    )

    ctx.say("The runtime suite ships with the adapter distribution. Run it:")
    report_path = ctx.dir / "conformance.json"
    proc = run_python(
        ["-m", "nornyx_agentic_adapters.conformance", "--summary", "--json", str(report_path)],
        cwd=ctx.dir,
    )
    from nornyx_lab.ui import command

    command(
        "python -m nornyx_agentic_adapters.conformance --summary",
        proc.returncode,
        (proc.stdout or proc.stderr)[:1400],
    )
    ctx.record("conformance_returncode", proc.returncode)

    if report_path.is_file():
        data = json.loads(report_path.read_text(encoding="utf-8"))
        ctx.record("conformance_keys", sorted(data.keys())[:8])
        ctx.note(f"report written to {report_path.name} ({len(json.dumps(data))} bytes)")

    ctx.concept(
        "--require is the anti-silent-skip mechanism",
        """
```bash
python -m nornyx_agentic_adapters.conformance --require crewai --require langgraph
```

Without `--require`, a missing optional extra makes the suite **skip** and report
green. A pipeline gating on that has been asserting nothing, possibly for months.

`--require` makes the absence of a framework a **failure**. This is Chapter 15's
rule made mechanical: a silently skipped test is a governance failure, not a
hygiene problem, and the fix is that the pipeline counts what it expected to run.
""",
    )

    # -------------------------------------------------- external enforcement
    ctx.section("What independent enforcement actually requires")

    ctx.say(
        """
Four properties, and having three is **not** a partial version of the fourth:

1. **Unavoidable placement** — every path to the effect traverses it.
2. **Separate trust domain** — the governed process cannot modify or disable it.
3. **Independent attestation** — it records what it did, in its own store.
4. **Fail-closed behaviour** — its own outage denies rather than permits.

An egress proxy with (1), (2), (4) but no (3) blocks without attesting. A
telemetry pipeline with (2), (3) but not (1) attests without blocking. Neither is
"most of the way there".
"""
    )

    ctx.say(
        """
| family | placement | evidence quality | blast radius on failure |
|---|---|---|---|
| API gateway / egress proxy | on the network path | good, but network-level semantics | everything behind it |
| Service mesh | between services | good for service-to-service | the mesh's scope |
| Sandbox / isolated worker | around the process | excellent, coarse | one workload |
| IAM / workload identity | at the resource | excellent, authoritative | the credential's scope |
| Platform-native policy engine | at the control plane | good, platform-shaped | the tenancy |

Nornyx is on none of these rows. It is the layer that *names* the actor, bounds
the action, and binds the evidence — and then hands enforcement to whichever row
sits on the path.
"""
    )

    ctx.concept(
        "the dual-evidence problem",
        """
The enforcement point blocks but does not know *why* in governance terms. The
governance layer knows why but did not block.

Combining them is not free: you now have **two records of one event**, produced
by two systems, on two clocks, with two identity models. Correlating them is a
real engineering cost, and if you do it badly you get a third failure mode —
records that disagree, with no way to tell which is right.

The related trap is **projection drift**: compiling your contract into an
external policy language (Rego, Cedar) creates a second artifact that can drift
from its source. A contract-only declaration model — what Nornyx implements
today — describes the boundary without projecting into it, which avoids drift by
declining to solve the problem.
""",
    )

    # ------------------------------------------------------------- protocols
    ctx.section("Protocol boundaries: declared, not executed")

    contract_text = (shared_contract("ledger") / "network.nyx").read_text(encoding="utf-8")
    start = contract_text.index("  protocol_targets:")
    ctx.code(contract_text[start : start + 900], "yaml", caption="a declared A2A boundary")

    ctx.say(
        """
Read what is **not** there: no endpoint, no credential, no command, no transport
setting. Those fields are **structurally unrepresentable** in this block.

`execution_mode: contract_only` and `live_connector_execution: false` are the
whole posture. The declaration says *this boundary exists, these categories may
cross it, this approval gates it* — and stops. MCP and A2A create a governance
**surface**; they are not a governance **solution**, and a declaration layer that
tried to also execute them would be exactly the fused appliance Chapter 2 warns
about.
"""
    )

    # ---------------------------------------------------------- package scan
    ctx.section("The supply chain: scanning a third-party tool pack")

    fixture = ctx.dir / "fixtures" / "suspicious-tool-pack"
    out = ctx.dir / "scan-out"
    shutil.rmtree(out, ignore_errors=True)

    ctx.code(
        (fixture / "README.md").read_text(encoding="utf-8")[:520],
        "markdown",
        caption="what the package says about itself",
    )
    ctx.code(
        (fixture / "install.sh").read_text(encoding="utf-8")[:700],
        "bash",
        caption="what the package actually does",
    )

    result = ctx.cli(
        nornyx(
            "package", "scan", str(fixture), "--out", str(out), "--package-id", "acme-agent-tools"
        ),
    )
    ctx.record("scan_ok", result.ok)

    analysis_path = out / "package_analysis.json"
    if analysis_path.is_file():
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        surface = analysis["risk_surface"]
        boundary = analysis["safety_boundary"]

        ctx.say(f"**Risk tier: `{surface['risk_tier']}`** — {surface['finding_count']} findings.")
        for explanation in surface["explanations"]:
            ctx.note(explanation)
        ctx.record("risk_tier", surface["risk_tier"])
        ctx.record("finding_count", surface["finding_count"])

        cve = json.loads((out / "claim_vs_evidence_report.json").read_text(encoding="utf-8"))
        if cve.get("mismatches"):
            mismatch = cve["mismatches"][0]
            ctx.code(
                json.dumps(
                    {
                        "claim": mismatch["claim"],
                        "claim_trust_level": mismatch["claim_trust_level"],
                        "finding_type": mismatch["evidence_record"]["finding_type"],
                        "severity": mismatch["evidence_record"]["severity"],
                        "recommendation": mismatch["evidence_record"]["recommendation"],
                    },
                    indent=2,
                ),
                "json",
                caption="a claim, refuted by evidence in the same package",
            )
            ctx.record("mismatch_claim", mismatch["claim"])

        ctx.concept(
            "untrusted self-description, made computable",
            """
The README asserted "no network calls are made". The scanner recorded that
assertion as an **`untrusted_claim`**, observed endpoints in `install.sh`, and
emitted a mismatch.

That is the whole idea: a package's description of itself is *data to be checked*,
not information to be believed. The scanner does not decide the package is
malicious — it makes the contradiction visible and routes it to a human.
""",
        )

        ctx.code(
            json.dumps(boundary, indent=2),
            "json",
            caption="what the scanner refused to do",
        )
        ctx.record("payload_executed", boundary["package_payload_executed"])

    ctx.boundary(
        """
**The scanner's code-asserted non-claims.** It did not execute the payload,
activate hooks, start MCP servers, use the network, or store raw secret values —
and it says so in a machine-readable block rather than in a README.

The strongest honest sentence a scan supports is:

> **inventoried, risk-surfaced, evidence-bound, hash-locked, and approval-gated**

Not "safe". Not "scanned and clean". A `critical` tier here means *a human must
look*, and the scan's value is that it made looking cheap and specific.
"""
    )

    ctx.tryit(
        """
1. Edit the fixture's `README.md` to drop the security claims, and re-scan. The
   risk tier stays `critical` — why? Which findings were never about the claims?
2. Point the scanner at a real dependency you already use:
   `nornyx package scan path/to/package --out /tmp/scan --package-id thing`.
   Read `risk_surface_report.md` before you read anything else.
"""
    )

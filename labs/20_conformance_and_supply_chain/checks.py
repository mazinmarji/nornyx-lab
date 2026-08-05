"""Concept checks for Lab 20."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from nornyx_lab.contract import nornyx, run_python, shared_contract
from nornyx_lab.optional import skip_unless

LAB = Path(__file__).parent
FIXTURE = LAB / "fixtures" / "suspicious-tool-pack"


def _scan(out: Path):
    shutil.rmtree(out, ignore_errors=True)
    result = nornyx(
        "package", "scan", str(FIXTURE), "--out", str(out), "--package-id", "acme-agent-tools"
    )
    assert result.ok, result.stdout + result.stderr
    return json.loads((out / "package_analysis.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------- conformance
def test_the_runtime_conformance_suite_runs_and_reports(tmp_path):
    report = tmp_path / "conformance.json"
    proc = run_python(
        ["-m", "nornyx_agentic_adapters.conformance", "--summary", "--json", str(report)]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data, "the suite must emit a report, not just an exit code"


def test_require_turns_a_missing_framework_into_a_failure(tmp_path):
    """The anti-silent-skip mechanism, verified rather than assumed."""
    proc = run_python(
        [
            "-m",
            "nornyx_agentic_adapters.conformance",
            "--require",
            "not_a_real_framework",
            "--json",
            str(tmp_path / "r.json"),
        ]
    )
    assert proc.returncode != 0, "requiring an unavailable framework must fail, not skip quietly"


def test_both_framework_suites_are_available_here(tmp_path):
    """CI installs the extras so nothing is skipped; assert that holds."""
    skip_unless("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    skip_unless("nornyx_agentic_adapters.langgraph", extra="langgraph")

    proc = run_python(
        [
            "-m",
            "nornyx_agentic_adapters.conformance",
            "--require",
            "crewai",
            "--require",
            "langgraph",
            "--json",
            str(tmp_path / "r.json"),
        ]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# -------------------------------------------------------------- protocol block
def test_a_protocol_target_cannot_carry_an_endpoint_or_credential():
    """Structurally unrepresentable, not merely discouraged."""
    text = (shared_contract("ledger") / "network.nyx").read_text(encoding="utf-8")
    start = text.index("  protocol_targets:")
    block = text[start : text.index("  network_gates:")]

    assert "execution_mode: contract_only" in block
    assert "live_connector_execution: false" in block

    # `credentials` and `tokens` DO appear here — inside `never_share`, which is
    # the opposite of leaking them. What must be absent is any key that could
    # carry a reachable target or a secret VALUE.
    for forbidden_key in ("endpoint:", "url:", "uri:", "host:", "command:", "token:", "secret:"):
        assert forbidden_key not in block.lower(), f"protocol block leaked {forbidden_key!r}"
    assert "https://" not in block, "a declared boundary carries no reachable address"


# -------------------------------------------------------------- package scan
def test_the_scan_flags_the_package_as_critical(tmp_path):
    analysis = _scan(tmp_path / "scan")
    assert analysis["risk_surface"]["risk_tier"] == "critical"
    assert analysis["risk_surface"]["finding_count"] > 0


def test_the_scan_never_executes_the_payload(tmp_path):
    """The scanner's code-asserted non-claims."""
    analysis = _scan(tmp_path / "scan")
    boundary = analysis["safety_boundary"]

    assert boundary["package_payload_executed"] is False
    assert boundary["hooks_activated"] is False
    assert boundary["mcp_servers_started"] is False
    assert boundary["network_used_by_builtin_scanner"] is False
    assert boundary["raw_secret_values_stored"] is False


def test_a_package_claim_is_recorded_as_untrusted_and_refuted(tmp_path):
    """Untrusted self-description, made computable."""
    out = tmp_path / "scan"
    _scan(out)
    report = json.loads((out / "claim_vs_evidence_report.json").read_text(encoding="utf-8"))

    assert report["claims"]["no_network"] is True, "the README claims it"
    assert report["mismatches"], "and the evidence must contradict it"

    mismatch = report["mismatches"][0]
    assert mismatch["claim"] == "no_network"
    assert mismatch["claim_trust_level"] == "untrusted_claim"
    assert mismatch["evidence_record"]["requires_human_review"] is True


def test_the_scan_is_deterministic(tmp_path):
    """A risk report that varies run to run cannot gate anything."""
    first = _scan(tmp_path / "a")
    second = _scan(tmp_path / "b")

    assert first["risk_surface"] == second["risk_surface"]
    assert first["source_hash"] == second["source_hash"]

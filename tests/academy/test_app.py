from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
        )
    )


def test_health_platform_catalog_and_security_headers(tmp_path) -> None:
    with _client(tmp_path) as client:
        health = client.get("/api/v1/health")
        platform = client.get("/api/v1/platform")
        catalog = client.get("/api/v1/catalog")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "api_version": "v1"}
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
    assert platform.status_code == 200
    assert platform.json()["nornyx_runtime_version"] == "1.11.0"
    assert platform.json()["nornyx_audited_main_commit"] == (
        "8d00029e6d3486a6aa348e1e113f7c6f7e6ebe1a"
    )
    assert len(catalog.json()["modules"]) == 31
    assert len(catalog.json()["paths"]) == 7


def test_default_demo_proves_a_real_governed_delta_and_records_execution(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/demo/run",
            json={
                "injection_enabled": True,
                "enforcement_enabled": True,
                "approval_state": "missing",
                "planner_mode": "deterministic",
            },
        )
        progress = client.get("/api/v1/progress")

    assert response.status_code == 200, response.text
    payload = response.json()
    comparison = {item["action"]: item for item in payload["comparison"]}
    assert comparison["publish_external"]["ungoverned"]["attempts"] == 1
    assert comparison["publish_external"]["ungoverned"]["completions"] == 1
    assert comparison["publish_external"]["governed"]["attempts"] == 0
    assert comparison["publish_external"]["governed"]["completions"] == 0
    assert payload["restored"] is True
    module = next(item for item in progress.json()["modules"] if item["module_id"] == "F0")
    assert module["executions"] == 1


def test_foundation_execution_and_assessment_are_distinct_completion_gates(tmp_path) -> None:
    with _client(tmp_path) as client:
        run = client.post("/api/v1/modules/F0/run")
        public = client.get("/api/v1/assessments/assessment.F0")
        definition = client.app.state.assessments.definition("assessment.F0")
        submission = client.post(
            "/api/v1/assessments/assessment.F0/submit",
            json={"answers": list(definition.correct)},
        )
        progress = client.get("/api/v1/progress")

    assert run.status_code == 200, run.text
    assert run.json()["module_id"] == "F0"
    assert run.json()["completion_eligible"] is True
    assert public.status_code == 200
    assert "correct" not in public.json()
    assert submission.status_code == 200
    assert submission.json()["passed"] is True
    module = next(item for item in progress.json()["modules"] if item["module_id"] == "F0")
    assert module["status"] == "complete"
    assert module["executions"] == 1
    assert module["assessment_attempts"] == 1


def test_unknown_module_and_assessment_return_clear_404s(tmp_path) -> None:
    with _client(tmp_path) as client:
        module = client.post("/api/v1/modules/nope/run")
        assessment = client.get("/api/v1/assessments/assessment.nope")

    assert module.status_code == 404
    assert "unknown curriculum module" in module.json()["detail"]
    assert assessment.status_code == 404
    assert "unknown assessment" in assessment.json()["detail"]


def test_dedicated_advanced_modules_are_routed_and_validate_inputs(tmp_path) -> None:
    with _client(tmp_path) as client:
        forge = client.post(
            "/api/v1/modules/22/run",
            json={"approval_state": "missing", "include_inert_bypass": True},
        )
        assurance = client.post(
            "/api/v1/modules/23/run",
            json={"include_direct_bypass": True},
        )
        invalid = client.post(
            "/api/v1/modules/22/run",
            json={"approval_state": "forged"},
        )

    assert forge.status_code == 200, forge.text
    assert forge.json()["module_id"] == "22"
    assert forge.json()["results"]["configuration"]["approval_state"] == "missing"
    bypass = forge.json()["results"]["incident"]["direct_in_process_bypass"]
    assert bypass["executed"] is True
    assert bypass["counter"]["completions"] == 1
    assert assurance.status_code == 200, assurance.text
    assert assurance.json()["module_id"] == "23"
    assert assurance.json()["results"]["configuration"]["include_direct_bypass"] is True
    assert invalid.status_code == 422
    assert "approval_state" in invalid.json()["detail"]


def test_contract_explorer_and_isolated_workbench_use_structured_results(tmp_path) -> None:
    with _client(tmp_path) as client:
        contracts = client.get("/api/v1/contracts")
        detail = client.get("/api/v1/contracts/atlas")
        validation = client.post(
            "/api/v1/contracts/workbench",
            json={
                "contract_id": "atlas",
                "mutations": [
                    {
                        "operation": "set_project_purpose",
                        "target": "project.purpose",
                        "value": "Browser workbench validation",
                    }
                ],
            },
        )

    assert contracts.status_code == 200, contracts.text
    assert {item["id"] for item in contracts.json()} == {"atlas", "ledger"}
    assert detail.status_code == 200, detail.text
    assert detail.json()["nodes"]
    assert detail.json()["assurance_boundary"]
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True
    assert validation.json()["semantic_paths_only"] is True


def test_live_secret_is_process_local_and_progress_can_export_then_reset(tmp_path) -> None:
    with _client(tmp_path) as client:
        enabled = client.put(
            "/api/v1/settings/live",
            json={
                "enabled": True,
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "api_key": "secret-test-value",
            },
        )
        exported = client.get("/api/v1/progress/export")
        reset = client.post("/api/v1/progress/reset")
        disabled = client.put(
            "/api/v1/settings/live",
            json={
                "enabled": False,
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "api_key": None,
            },
        )

    assert enabled.status_code == 200
    assert enabled.json()["configured"] is True
    assert "secret-test-value" not in enabled.text
    assert exported.status_code == 200
    assert exported.json()["schema_id"] == "nornyx.academy.progress.v1"
    assert "secret-test-value" not in exported.text
    assert reset.json()["completed_modules"] == 0
    assert disabled.json()["configured"] is False

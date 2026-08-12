"""Verify the H1-D feedback-gateway provisioning against real state.

Every check here reads actual state — GitHub's answer about the intake
repository, the deployed endpoint's TLS and health response, the container
topology docker reports, the raw configuration files — rather than trusting
what a deploy command printed. The checks are the machine-readable form of
the H1-D start gate:

    private intake repository, queried from GitHub;
    HTTPS endpoint with valid TLS and an honest /health;
    exactly one replica, with no path to more;
    a persistent volume mounted at /var/lib/nornyx-feedback;
    the gateway database on that volume;
    no credential in source, image history, logs, or database.

``--self-test`` proves the checks are load-bearing by feeding each one a
deliberately broken fixture — no volume, two replicas, a public repository
claimed private, a planted credential — and requiring it to fail, alongside
a healthy twin that must pass. A verifier that cannot fail verifies nothing.

Secrets are never printed. Log and database scans report only whether a
credential-shaped value was found, never the value.

Usage:

    python scripts/verify_h1d_provisioning.py --self-test
    python scripts/verify_h1d_provisioning.py \
        --repository mazinmarji/nornyx-lab-feedback \
        --expect-visibility private \
        --endpoint https://<host>/ \
        --compose-file ops/feedback-gateway/compose.production.yaml \
        --container nornyx-feedback-gateway \
        --fly-config ops/feedback-gateway/fly.toml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

VOLUME_TARGET = "/var/lib/nornyx-feedback"
DB_PATH = "/var/lib/nornyx-feedback/gateway.db"
TOKEN_ENV = "NORNYX_FEEDBACK_GITHUB_TOKEN"  # noqa: S105 — the variable's *name*

#: Credential-shaped content. The classic and fine-grained GitHub token
#: prefixes, plus any long bare secret assigned to the token variable.
TOKEN_SHAPE = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
ASSIGNED_TOKEN = re.compile(
    rf"{TOKEN_ENV}\s*[=:]\s*[\"']?(?!\s|\$|\{{|<|\.\.\.)([A-Za-z0-9_-]{{20,}})"
)


@dataclass
class Report:
    """Accumulated check results; the process exit code is its verdict."""

    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, name: str, ok: bool, evidence: str) -> bool:
        self.results.append((name, ok, evidence))
        return ok

    def render(self) -> str:
        lines = []
        for name, ok, evidence in self.results:
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}: {evidence}")
        failed = sum(1 for _, ok, _ in self.results if not ok)
        lines.append(
            f"{len(self.results) - failed}/{len(self.results)} checks passed"
            + (f", {failed} FAILED" if failed else "")
        )
        return "\n".join(lines)

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.results)


def _run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


# --------------------------------------------------------------------------
# Repository


def check_repository(
    report: Report,
    repository: str,
    expected_visibility: str,
    repo_info: dict | None = None,
) -> None:
    """The intake repository must exist and actually have the configured visibility.

    ``repo_info`` is injected by the self-test; the real path asks GitHub.
    """

    if repo_info is None:
        code, output = _run(["gh", "api", f"repos/{repository}"])
        if code != 0:
            report.record("repository exists", False, f"gh api repos/{repository} failed")
            return
        repo_info = json.loads(output)

    owner, _, name = repository.partition("/")
    report.record(
        "repository exists",
        repo_info.get("full_name") == repository,
        f"GitHub reports {repo_info.get('full_name')!r}",
    )
    report.record(
        "repository owner",
        repo_info.get("owner", {}).get("login") == owner,
        f"owner is {repo_info.get('owner', {}).get('login')!r}",
    )
    actual = repo_info.get("visibility")
    report.record(
        "repository visibility matches configuration",
        actual == expected_visibility
        and repo_info.get("private") == (expected_visibility == "private"),
        f"configured {expected_visibility!r}, GitHub reports {actual!r} (private={repo_info.get('private')})",
    )
    report.record(
        "repository issues enabled",
        repo_info.get("has_issues") is True,
        f"has_issues={repo_info.get('has_issues')}",
    )


# --------------------------------------------------------------------------
# Endpoint


def _fetch_health(health_url: str) -> tuple[int, str]:
    with urllib.request.urlopen(health_url, timeout=10) as response:  # noqa: S310
        return response.status, response.read().decode("utf-8")


def check_endpoint(
    report: Report,
    endpoint: str,
    expected_visibility: str,
    allow_loopback_http: bool = False,
    expect_github_configured: bool = True,
    health_fetch: Callable[[str], tuple[int, str]] | None = None,
) -> None:
    """The endpoint must be HTTPS with valid TLS and an honest, secretless /health.

    ``health_fetch`` is injected by the self-test so the health-honesty checks
    can be driven with fixture responses; the real path performs the request.
    """

    parsed = urllib.parse.urlsplit(endpoint)
    loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not (loopback and allow_loopback_http):
        report.record("endpoint is HTTPS", False, f"scheme is {parsed.scheme!r}")
        return
    report.record(
        "endpoint is HTTPS",
        True,
        "https" if parsed.scheme == "https" else "loopback http accepted for staging only",
    )
    if "@" in parsed.netloc or TOKEN_SHAPE.search(endpoint):
        report.record("no credential in URL", False, "endpoint carries userinfo or a token")
        return
    report.record("no credential in URL", True, "clean URL")

    if parsed.scheme == "https":
        try:
            with ssl.create_default_context().wrap_socket(
                socket.create_connection((parsed.hostname, parsed.port or 443), 10),
                server_hostname=parsed.hostname,
            ) as tls:
                peer = tls.getpeercert() or {}
            issuer = dict(x[0] for x in peer.get("issuer", ()) if x)
            report.record(
                "TLS certificate valid",
                True,
                f"issuer {issuer.get('organizationName', '?')!r}, expires {peer.get('notAfter', '?')}",
            )
        except (ssl.SSLError, OSError) as error:
            report.record("TLS certificate valid", False, f"{type(error).__name__}: {error}")
            return

    health_url = endpoint.rstrip("/") + "/health"
    try:
        status, body = (health_fetch or _fetch_health)(health_url)
    except (urllib.error.URLError, OSError) as error:
        report.record("health endpoint responds", False, f"{type(error).__name__}: {error}")
        return
    report.record("health endpoint responds", status == 200, f"GET /health -> {status}")

    try:
        health = json.loads(body)
    except json.JSONDecodeError:
        report.record("health response is JSON", False, "body is not JSON")
        return
    report.record(
        "health reports a configured GitHub destination",
        health.get("github_configured") is expect_github_configured,
        f"github_configured={health.get('github_configured')} (expected {expect_github_configured})",
    )
    report.record(
        "health visibility matches configuration",
        health.get("destination_visibility") == expected_visibility,
        f"destination_visibility={health.get('destination_visibility')!r}",
    )
    report.record(
        "health response carries no secret",
        not TOKEN_SHAPE.search(body) and "token" not in {k.lower() for k in health},
        "no credential-shaped content in /health",
    )


# --------------------------------------------------------------------------
# Compose topology


def check_compose_topology(report: Report, config: dict, raw_text: str) -> None:
    """One replica, the right volume target, the right DB path, no inline secret.

    ``config`` is the parsed output of ``docker compose config --format json``;
    ``raw_text`` is the file as committed, which is where a pasted secret or a
    hardcoded token would live.
    """

    services = config.get("services", {})
    report.record(
        "compose defines exactly one service", len(services) == 1, f"{len(services)} services"
    )
    if not services:
        return
    service = next(iter(services.values()))

    replicas = (service.get("deploy") or {}).get("replicas", 1)
    pinned_name = bool(service.get("container_name"))
    report.record(
        "compose pins exactly one replica",
        replicas == 1 and pinned_name,
        f"deploy.replicas={replicas}, container_name={'set' if pinned_name else 'MISSING'}",
    )

    targets = [
        volume.get("target") if isinstance(volume, dict) else str(volume).split(":")[1]
        for volume in service.get("volumes", [])
    ]
    report.record(
        "compose mounts the persistent volume",
        VOLUME_TARGET in targets,
        f"mount targets: {targets or 'NONE'}",
    )

    environment = service.get("environment", {})
    if isinstance(environment, list):
        environment = dict(item.split("=", 1) for item in environment if "=" in item)
    report.record(
        "compose puts the database on the volume",
        str(environment.get("NORNYX_FEEDBACK_DB", "")).startswith(VOLUME_TARGET + "/"),
        f"NORNYX_FEEDBACK_DB={environment.get('NORNYX_FEEDBACK_DB')!r}",
    )

    report.record(
        "compose file carries no secret value",
        not TOKEN_SHAPE.search(raw_text) and not ASSIGNED_TOKEN.search(raw_text),
        f"{TOKEN_ENV} appears only as an interpolated runtime variable",
    )


# --------------------------------------------------------------------------
# Fly topology


def check_fly_topology(report: Report, fly_toml_text: str) -> None:
    """The committed Fly configuration must pin the same topology."""

    config = tomllib.loads(fly_toml_text)

    mounts = config.get("mounts", [])
    destinations = [mount.get("destination") for mount in mounts]
    report.record(
        "fly config mounts the persistent volume",
        destinations == [VOLUME_TARGET],
        f"mount destinations: {destinations or 'NONE'}",
    )

    env = config.get("env", {})
    report.record(
        "fly config puts the database on the volume",
        str(env.get("NORNYX_FEEDBACK_DB", "")).startswith(VOLUME_TARGET + "/"),
        f"NORNYX_FEEDBACK_DB={env.get('NORNYX_FEEDBACK_DB')!r}",
    )
    report.record(
        "fly config carries no secret",
        TOKEN_ENV not in env and not TOKEN_SHAPE.search(fly_toml_text),
        f"{TOKEN_ENV} absent from [env]; no token-shaped content",
    )

    service = config.get("http_service", {})
    report.record(
        "fly config forces HTTPS",
        service.get("force_https") is True,
        f"force_https={service.get('force_https')}",
    )
    report.record(
        "fly config keeps one machine always running",
        service.get("auto_stop_machines") is False and service.get("min_machines_running") == 1,
        f"auto_stop_machines={service.get('auto_stop_machines')}, "
        f"min_machines_running={service.get('min_machines_running')}",
    )
    report.record(
        "fly config serves the gateway port",
        service.get("internal_port") == 8080,
        f"internal_port={service.get('internal_port')}",
    )


def check_fly_machines(report: Report, machines: list[dict]) -> None:
    """The running Fly app must have exactly one started machine."""

    started = [machine for machine in machines if machine.get("state") == "started"]
    report.record(
        "exactly one machine running",
        len(machines) == 1 and len(started) == 1,
        f"{len(machines)} machines, {len(started)} started",
    )
    for machine in machines:
        mounts = [mount.get("path") for mount in machine.get("config", {}).get("mounts", [])]
        report.record(
            "running machine mounts the volume",
            VOLUME_TARGET in mounts,
            f"machine {machine.get('id', '?')} mounts: {mounts or 'NONE'}",
        )


# --------------------------------------------------------------------------
# Running container (docker host / staging)


#: Probe executed inside the running service (docker exec / fly ssh): the
#: database must exist on the volume and carry no credential-shaped bytes.
DB_PROBE = (
    "import pathlib,re,sys;"
    f"data = pathlib.Path({DB_PATH!r}).read_bytes();"
    r"sys.exit(2 if re.search(rb'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}', data) else 0)"
)

Runner = Callable[[list[str]], tuple[int, str]]


def check_running_container(report: Report, container: str, runner: Runner = _run) -> None:
    """The live container must match the topology the files promise.

    ``runner`` is injected by the self-test to drive every probe with fixture
    output; the real path shells out to docker.
    """

    code, output = runner(["docker", "inspect", container])
    if code != 0:
        report.record("container running", False, f"docker inspect {container} failed")
        return
    info = json.loads(output)[0]
    report.record(
        "container running",
        info["State"]["Running"] is True,
        f"state={info['State']['Status']}",
    )

    mounts = [
        mount for mount in info.get("Mounts", []) if mount.get("Destination") == VOLUME_TARGET
    ]
    report.record(
        "persistent volume mounted",
        len(mounts) == 1 and mounts[0].get("Type") == "volume",
        f"{VOLUME_TARGET} <- {mounts[0].get('Name') if mounts else 'NOTHING'}",
    )

    code, uid = runner(["docker", "exec", container, "id", "-u"])
    report.record(
        "container runs non-root",
        code == 0 and uid.strip().isdigit() and int(uid.strip()) != 0,
        f"uid={uid.strip()}",
    )

    image = info.get("Config", {}).get("Image", "")
    code, history = runner(["docker", "history", "--no-trunc", image])
    report.record(
        "no credential in image history",
        code == 0 and not TOKEN_SHAPE.search(history) and TOKEN_ENV + "=" not in history,
        f"docker history {image}: clean",
    )

    code, logs = runner(["docker", "logs", container])
    token = os.environ.get(TOKEN_ENV, "")
    leaked = bool(token and token in logs) or bool(TOKEN_SHAPE.search(logs))
    report.record(
        "no credential in container logs",
        code == 0 and not leaked,
        "log scan clean" if code == 0 else "docker logs failed - nothing was scanned",
    )

    code, _ = runner(["docker", "exec", container, "python", "-c", DB_PROBE])
    report.record(
        "database exists on the volume and carries no credential",
        code == 0,
        f"{DB_PATH} present, no token-shaped bytes" if code == 0 else f"probe exit {code}",
    )


def check_fly_runtime(report: Report, app: str, runner: Runner = _run) -> None:
    """Runtime security proofs for the deployed Fly machine.

    The docker-host checks cannot run against Fly, so the same three proofs
    go through flyctl: non-root process, database on the volume with no
    credential-shaped bytes, and no token-shaped content in the service
    logs. The log scan matches token *shapes* only — this process never
    holds the real secret value, by design.
    """

    code, output = runner(["flyctl", "ssh", "console", "--app", app, "-C", "id -u"])
    uids = [line.strip() for line in output.splitlines() if line.strip().isdigit()]
    report.record(
        "fly machine runs non-root",
        code == 0 and bool(uids) and all(uid != "0" for uid in uids),
        f"uid={uids[-1] if uids else '?'}" if code == 0 else "fly ssh console failed",
    )

    code, _ = runner(["flyctl", "ssh", "console", "--app", app, "-C", f'python -c "{DB_PROBE}"'])
    report.record(
        "fly database exists on the volume and carries no credential",
        code == 0,
        f"{DB_PATH} present, no token-shaped bytes" if code == 0 else f"probe exit {code}",
    )

    code, logs = runner(["flyctl", "logs", "--app", app, "--no-tail"])
    report.record(
        "no token-shaped content in fly logs",
        code == 0 and not TOKEN_SHAPE.search(logs),
        "log scan clean (token shapes)"
        if code == 0
        else "flyctl logs failed - nothing was scanned",
    )


# --------------------------------------------------------------------------
# Source tree secret scan


def scan_tree_for_secrets(report: Report, files: dict[str, str]) -> None:
    """No tracked file may carry a credential or assign the token variable a value."""

    offenders = [
        path
        for path, text in files.items()
        if TOKEN_SHAPE.search(text) or ASSIGNED_TOKEN.search(text)
    ]
    report.record(
        "no credential in tracked source",
        not offenders,
        f"scanned {len(files)} files" + (f"; OFFENDERS: {offenders}" if offenders else ""),
    )


def tracked_files(root: Path) -> dict[str, str]:
    code, output = _run(["git", "-C", str(root), "ls-files"])
    if code != 0:
        raise SystemExit("git ls-files failed — run from within the repository")
    files: dict[str, str] = {}
    for line in output.splitlines():
        path = root / line.strip()
        if path.is_file():
            try:
                files[line.strip()] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return files


# --------------------------------------------------------------------------
# Negative controls


def self_test() -> Report:
    """Prove each check can fail. A gate that cannot fail gates nothing."""

    outer = Report()

    def expect(name: str, broken: Report, healthy: Report) -> None:
        outer.record(
            f"negative control: {name}",
            (not broken.ok) and healthy.ok,
            f"broken fixture {'FAILED as required' if not broken.ok else 'WRONGLY PASSED'}; "
            f"healthy twin {'passed' if healthy.ok else 'WRONGLY FAILED'}",
        )

    good_repo = {
        "full_name": "owner/intake",
        "owner": {"login": "owner"},
        "visibility": "private",
        "private": True,
        "has_issues": True,
    }
    broken, healthy = Report(), Report()
    check_repository(
        broken, "owner/intake", "private", {**good_repo, "visibility": "public", "private": False}
    )
    check_repository(healthy, "owner/intake", "private", good_repo)
    expect("visibility mismatch (configured=private, actual=public)", broken, healthy)

    good_service = {
        "container_name": "gateway",
        "deploy": {"replicas": 1},
        "volumes": [{"target": VOLUME_TARGET}],
        "environment": {"NORNYX_FEEDBACK_DB": DB_PATH},
    }
    good_compose = {"services": {"gateway": good_service}}
    clean_text = f"environment:\n  {TOKEN_ENV}: ${{{TOKEN_ENV}:?runtime}}\n"

    broken, healthy = Report(), Report()
    check_compose_topology(
        broken,
        {"services": {"gateway": {**good_service, "volumes": []}}},
        clean_text,
    )
    check_compose_topology(healthy, good_compose, clean_text)
    expect("missing persistent volume", broken, healthy)

    broken, healthy = Report(), Report()
    check_compose_topology(
        broken,
        {"services": {"gateway": {**good_service, "deploy": {"replicas": 2}}}},
        clean_text,
    )
    check_compose_topology(healthy, good_compose, clean_text)
    expect("replica count above one", broken, healthy)

    # The planted credential is assembled at runtime so no token-shaped
    # literal is ever committed to this repository, even a fake one.
    fake_token = "ghp_" + "A" * 36
    broken, healthy = Report(), Report()
    scan_tree_for_secrets(broken, {"deploy/env.sh": f"export {TOKEN_ENV}={fake_token}\n"})
    scan_tree_for_secrets(healthy, {"deploy/env.sh": f"export {TOKEN_ENV}=${{VAULT_REF}}\n"})
    expect("credential planted in tracked source", broken, healthy)

    broken, healthy = Report(), Report()
    fly_good = (
        f'[[mounts]]\ndestination = "{VOLUME_TARGET}"\n\n[env]\n'
        f'NORNYX_FEEDBACK_DB = "{DB_PATH}"\n\n[http_service]\n'
        "internal_port = 8080\nforce_https = true\nauto_stop_machines = false\n"
        "min_machines_running = 1\n"
    )
    check_fly_topology(
        broken, fly_good.replace("min_machines_running = 1", "min_machines_running = 0")
    )
    check_fly_topology(healthy, fly_good)
    expect("fly config that lets the last machine stop", broken, healthy)

    broken, healthy = Report(), Report()
    check_fly_machines(
        broken, [{"state": "started", "config": {"mounts": [{"path": VOLUME_TARGET}]}}] * 2
    )
    check_fly_machines(
        healthy, [{"state": "started", "config": {"mounts": [{"path": VOLUME_TARGET}]}}]
    )
    expect("two machines running", broken, healthy)

    # ---- endpoint honesty, driven with injected health responses --------
    good_health = json.dumps({"github_configured": True, "destination_visibility": "private"})

    def endpoint_with(response_body: str) -> Report:
        result = Report()
        check_endpoint(
            result,
            "http://127.0.0.1:1/",
            "private",
            allow_loopback_http=True,
            health_fetch=lambda url: (200, response_body),
        )
        return result

    broken, healthy = Report(), Report()
    check_endpoint(broken, "http://intake.example/", "private")
    check_endpoint(
        healthy,
        "http://127.0.0.1:1/",
        "private",
        allow_loopback_http=True,
        health_fetch=lambda url: (200, good_health),
    )
    expect("endpoint over plain HTTP off loopback", broken, healthy)

    expect(
        "health that reports no GitHub destination",
        endpoint_with(
            json.dumps({"github_configured": False, "destination_visibility": "private"})
        ),
        endpoint_with(good_health),
    )
    expect(
        "token-shaped content in the health response",
        endpoint_with(
            json.dumps(
                {"github_configured": True, "destination_visibility": "private", "note": fake_token}
            )
        ),
        endpoint_with(good_health),
    )

    # ---- running-container proofs, driven with a fixture docker ---------
    def fake_docker(overrides: dict[str, tuple[int, str]]) -> Runner:
        inspect_payload = json.dumps(
            [
                {
                    "State": {"Running": True, "Status": "running"},
                    "Mounts": [{"Type": "volume", "Name": "vol", "Destination": VOLUME_TARGET}],
                    "Config": {"Image": "gateway:test"},
                }
            ]
        )
        base = {
            "inspect": (0, inspect_payload),
            "exec-id": (0, "999\n"),
            "history": (0, "IMAGE CREATED CREATED BY\n<missing> uv sync --frozen\n"),
            "logs": (0, "INFO: application startup complete\n"),
            "exec-python": (0, ""),
        }
        table = {**base, **overrides}

        def runner(command: list[str]) -> tuple[int, str]:
            kind = command[1]
            if kind == "exec":
                kind = "exec-id" if command[3] == "id" else "exec-python"
            return table[kind]

        return runner

    def container_with(overrides: dict[str, tuple[int, str]]) -> Report:
        result = Report()
        check_running_container(result, "gateway", runner=fake_docker(overrides))
        return result

    expect("container running as root", container_with({"exec-id": (0, "0\n")}), container_with({}))
    no_mount = json.dumps(
        [
            {
                "State": {"Running": True, "Status": "running"},
                "Mounts": [],
                "Config": {"Image": "gateway:test"},
            }
        ]
    )
    expect(
        "container without the volume mount",
        container_with({"inspect": (0, no_mount)}),
        container_with({}),
    )
    expect(
        "token-shaped content in container logs",
        container_with({"logs": (0, f"boot\n{fake_token}\n")}),
        container_with({}),
    )
    expect(
        "unreadable container logs treated as scanned",
        container_with({"logs": (1, "configured logging driver does not support reading")}),
        container_with({}),
    )
    expect(
        "credential in image history",
        container_with({"history": (0, f"RUN export {TOKEN_ENV}={fake_token}\n")}),
        container_with({}),
    )
    expect(
        "missing database on the volume",
        container_with({"exec-python": (1, "FileNotFoundError")}),
        container_with({}),
    )

    # ---- fly runtime proofs, driven with a fixture flyctl ---------------
    def fake_flyctl(overrides: dict[str, tuple[int, str]]) -> Runner:
        base = {
            "ssh-id": (0, "Connecting to fdaa:0:1\n999\n"),
            "ssh-python": (0, ""),
            "logs": (0, "app[e286] iad [info] INFO: startup complete\n"),
        }
        table = {**base, **overrides}

        def runner(command: list[str]) -> tuple[int, str]:
            if command[1] == "logs":
                return table["logs"]
            return table["ssh-id" if command[-1] == "id -u" else "ssh-python"]

        return runner

    def fly_with(overrides: dict[str, tuple[int, str]]) -> Report:
        result = Report()
        check_fly_runtime(result, "app", runner=fake_flyctl(overrides))
        return result

    expect(
        "fly machine running as root",
        fly_with({"ssh-id": (0, "Connecting\n0\n")}),
        fly_with({}),
    )
    expect(
        "token-shaped content in fly logs",
        fly_with({"logs": (0, f"app[e286] {fake_token}\n")}),
        fly_with({}),
    )

    return outer


# --------------------------------------------------------------------------
# Entry point


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run the negative controls")
    parser.add_argument("--repository", help="owner/name of the intake repository")
    parser.add_argument("--expect-visibility", default="private", choices=["public", "private"])
    parser.add_argument("--endpoint", help="deployed gateway base URL")
    parser.add_argument("--allow-loopback-http", action="store_true")
    parser.add_argument(
        "--expect-unconfigured-github",
        action="store_true",
        help="pre-credential deployments report github_configured=false",
    )
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument("--fly-config", type=Path)
    parser.add_argument(
        "--fly-machines-json",
        type=Path,
        help="output of `flyctl machines list --json` for replica verification",
    )
    parser.add_argument("--container", help="running container name to inspect")
    parser.add_argument(
        "--fly-app",
        help="deployed Fly app name for runtime proofs (non-root, database, log scan)",
    )
    parser.add_argument("--scan-tree", type=Path, help="repository root to scan for secrets")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        report = self_test()
        print(report.render())
        return 0 if report.ok else 1

    report = Report()
    if arguments.repository:
        check_repository(report, arguments.repository, arguments.expect_visibility)
    if arguments.endpoint:
        check_endpoint(
            report,
            arguments.endpoint,
            arguments.expect_visibility,
            allow_loopback_http=arguments.allow_loopback_http,
            expect_github_configured=not arguments.expect_unconfigured_github,
        )
    if arguments.compose_file:
        code, output = _run(
            ["docker", "compose", "-f", str(arguments.compose_file), "config", "--format", "json"]
        )
        if code != 0:
            report.record("compose config parses", False, output.strip()[-200:])
        else:
            check_compose_topology(
                report, json.loads(output), arguments.compose_file.read_text(encoding="utf-8")
            )
    if arguments.fly_config:
        check_fly_topology(report, arguments.fly_config.read_text(encoding="utf-8"))
    if arguments.fly_machines_json:
        check_fly_machines(
            report, json.loads(arguments.fly_machines_json.read_text(encoding="utf-8"))
        )
    if arguments.container:
        check_running_container(report, arguments.container)
    if arguments.fly_app:
        check_fly_runtime(report, arguments.fly_app)
    if arguments.scan_tree:
        scan_tree_for_secrets(report, tracked_files(arguments.scan_tree))

    if not report.results:
        parser.error("nothing to verify — pass --self-test or at least one target")
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

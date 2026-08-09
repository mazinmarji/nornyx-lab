"""Guards on the independent deployment verification bundle (B5).

The bundle claims something CI cannot: that the documented path works on a
machine nobody prepared. Two properties make that claim meaningful, and both are
easy to lose in a later edit.

  - **It must not install prerequisites.** A script that apt-gets its way to a
    working machine and then reports success has proved that it can prepare
    machines, not that the product is portable.
  - **An environment failure must not read as a product failure.** An
    intercepting proxy and a broken Dockerfile produce the same red output.
    Collapsing them would either excuse a real defect or invent one.
"""

from __future__ import annotations

import re
import stat

from nornyx_lab.engine import repo_root

ROOT = repo_root()
SCRIPT = ROOT / "scripts" / "verify_independent_deployment.sh"
DOC = ROOT / "docs" / "INDEPENDENT_VERIFICATION.md"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_bundle_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), "the verification script is missing"
    assert DOC.is_file(), "the operator procedure is missing"
    mode = SCRIPT.stat().st_mode
    # On Windows checkouts the bit is carried by git rather than the filesystem,
    # so accept either, but the shebang must be there for `./script` to work.
    assert _script().startswith("#!/usr/bin/env bash")
    assert mode & stat.S_IRUSR


def test_the_procedure_is_linked_from_the_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/INDEPENDENT_VERIFICATION.md" in readme


# --------------------------------------------------- it must not fix the machine
def test_the_script_never_installs_a_prerequisite() -> None:
    """The whole claim collapses if the script prepares the machine itself."""
    installers = re.compile(
        r"\b("
        r"apt-get\s+install|apt\s+install|yum\s+install|dnf\s+install|apk\s+add"
        r"|brew\s+install|choco\s+install|winget\s+install"
        r"|pip\s+install|pip3\s+install|uv\s+pip\s+install"
        r"|npm\s+(install|i)\s+-g|npm\s+install\s+--global"
        r"|curl[^\n]*\|\s*(ba)?sh"
        r")\b",
        re.IGNORECASE,
    )
    hit = installers.search(_script())
    assert not hit, f"the verification script installs a prerequisite: {hit.group(0)!r}"


def test_the_script_does_not_weaken_tls_or_set_a_proxy() -> None:
    """Trusting an arbitrary certificate to make the build pass would turn the
    portability check into a demonstration that TLS can be disabled."""
    dangerous = re.compile(
        r"(curl[^\n]*\s-k\b|--insecure|NODE_TLS_REJECT_UNAUTHORIZED|strict-ssl[= ]false"
        r"|npm\s+config\s+set\s+(cafile|proxy|https-proxy)|GIT_SSL_NO_VERIFY)",
        re.IGNORECASE,
    )
    hit = dangerous.search(_script())
    assert not hit, f"the script tampers with transport trust: {hit.group(0)!r}"


# ------------------------------------------------ environment vs product failure
def test_environment_and_product_failures_are_counted_separately() -> None:
    script = _script()
    assert "ENVIRONMENT_FAILURES" in script
    assert "PRODUCT_FAILURES" in script
    # And they must produce different exit codes.
    assert re.search(r"EXIT_CODE=2", script), "environment failure must exit 2"
    assert re.search(r"EXIT_CODE=1", script), "product failure must exit 1"


def test_a_registry_failure_during_build_is_classified_as_environmental() -> None:
    """This is the specific confusion the development machine would cause."""
    script = _script()
    classifier = re.search(
        r"grep -qiE \"([^\"]+)\" \"\$\{EVIDENCE_DIR\}/docker-build\.txt\"", script
    )
    assert classifier, "the build failure path does not inspect the log to classify the cause"
    pattern = classifier.group(1)
    for symptom in ("certificate", "UNABLE_TO_VERIFY", "ECONNRESET", "resolve"):
        assert symptom.lower() in pattern.lower(), (
            f"a build failure containing {symptom!r} would be misreported as a product defect"
        )


def test_the_documented_exit_codes_match_the_script() -> None:
    doc = DOC.read_text(encoding="utf-8")
    for code, meaning in (("0", "pass"), ("1", "product-failure"), ("2", "environment-failure")):
        assert f"`{code}`" in doc, f"exit {code} is not documented"
        assert meaning in doc, f"{meaning} is not explained in the procedure"


# --------------------------------------------------------- what it actually does
def test_it_waits_for_health_rather_than_sleeping_blindly() -> None:
    script = _script()
    assert "/api/v1/health" in script
    assert "HEALTH_TIMEOUT" in script
    assert re.search(r"while \[ \"\$WAITED\" -lt \"\$HEALTH_TIMEOUT\" \]", script), (
        "health must be polled with a bounded loop, not waited on with a fixed sleep"
    )


def test_it_builds_without_a_useful_cache() -> None:
    assert "--no-cache" in _script(), (
        "a cached build cannot distinguish 'builds from nothing' from 'builds here'"
    )


def test_it_requires_the_conditional_zero_zero_semantics() -> None:
    """0/0 alone is not a prevention; an action nobody planned records 0/0 too.

    The check must require the ungoverned 1/1 as well, and must look at the
    meaning rather than only the numbers.
    """
    script = _script()
    assert "prevented_before_execution" in script
    assert '"executed"' in script or "'executed'" in script
    assert "not_planned" in DOC.read_text(encoding="utf-8"), (
        "the procedure must explain why 0/0 alone would not be enough"
    )


def test_it_exercises_the_running_production_service() -> None:
    script = _script()
    assert "/api/v1/demo/run" in script, "the scenario must run through the service, not in tests"
    assert "docker compose up" in script
    assert "docker compose restart" in script, "persistence is only shown across a restart"


def test_it_captures_evidence_and_a_verdict() -> None:
    script = _script()
    assert "verdict.json" in script
    assert "environment.txt" in script
    for artifact in ("docker-build", "health.json", "demo-run.json", "container-logs.txt"):
        assert artifact in script, f"{artifact} is not captured as evidence"


# ------------------------- the verifier must not be the portability dependency
def test_the_harness_never_requires_a_host_python() -> None:
    """The verifier cannot become the thing that fails to port.

    The first version told an operator who had installed exactly what the
    documentation asked for — Docker and Compose — to "install python and
    re-run". CI could never surface it: GitHub runners already carry Python,
    Node, git and curl, so the harness's own dependencies were invisible.

    Every Python invocation must therefore run inside the built image.
    """
    script = _script()

    # No message may ever ask the operator for a Python.
    for line in script.splitlines():
        if "envfail" in line or "fail " in line:
            assert "python" not in line.lower(), (
                f"the harness asks the operator for a Python runtime: {line.strip()[:90]!r}"
            )

    # Every `python` execution is a container execution.
    for match in re.finditer(r"^[^#\n]*\bpython3?\b[^\n]*$", script, re.MULTILINE):
        line = match.group(0)
        if "host_python_present_but_unused" in line:
            continue  # informational record, gates nothing
        assert "docker run" in line or "entrypoint python" in line, (
            f"this line runs a host Python: {line.strip()[:90]!r}"
        )

    # And the interpreter must come from the image under test.
    assert 'docker run --rm -i --entrypoint python "$IMAGE_TAG"' in script


def test_harness_prerequisites_are_checked_before_the_build_and_named_as_such() -> None:
    """An operator should learn about a missing `curl` in seconds, not after a
    fifteen-minute build, and should be told whose requirement it is."""
    script = _script()

    assert re.search(r"for tool in curl git; do", script), (
        "the harness does not check its own prerequisites"
    )
    assert "required by this verification script, not by the product" in script, (
        "a harness prerequisite must not read as a product prerequisite"
    )
    assert script.index("for tool in curl git") < script.index("--no-cache"), (
        "harness prerequisites must be checked before the expensive build"
    )


def test_the_port_probe_adds_no_dependency() -> None:
    """The probe itself must not need an interpreter."""
    script = _script()
    assert "/dev/tcp/127.0.0.1/8000" in script, "use bash's own socket rather than a helper runtime"


def test_the_procedure_separates_the_three_kinds_of_prerequisite() -> None:
    doc = DOC.read_text(encoding="utf-8")
    assert "Prerequisites, in three kinds" in doc
    assert "Verification harness" in doc
    assert "Not required on the host" in doc
    # The three lists must actually disagree with each other.
    harness = doc[doc.index("Verification harness") : doc.index("Not required on the host")]
    excluded = doc[doc.index("Not required on the host") :][:400]
    assert "curl" in harness and "git" in harness
    for absent in ("Python", "Node", "npm"):
        assert absent in excluded, f"{absent} must be named as not required on the host"
        assert absent.lower() not in harness.lower(), f"{absent} is listed as a harness need"


# ------------------------------- defects the first real run exposed, now pinned
def test_a_verdict_is_written_from_the_exit_trap() -> None:
    """Early exits must still leave a verdict.

    The first run stopped at step 5 and produced no verdict.json at all, while
    the procedure tells the operator to attach exactly that file. An operator
    left with logs and no verdict has evidence they cannot interpret.
    """
    script = _script()
    assert "write_verdict()" in script
    assert re.search(r"cleanup\(\)\s*\{\s*\n\s*write_verdict", script), (
        "the verdict must be written from the EXIT trap, not only on the happy path"
    )
    assert "reached_step" in script, "a partial run must say how far it got"


def test_the_verdict_is_valid_json() -> None:
    """A raw newline inside a JSON string makes the file unparseable.

    The first version emitted the note across three `echo` lines and produced a
    verdict.json that no tool could read.
    """
    script = _script()
    body = script[script.index("write_verdict()") : script.index("cleanup()")]
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith('echo "'):
            continue
        # Every emitted JSON line must close the quotes it opens.
        assert stripped.count('\\"') % 2 == 0, (
            f"this line leaves a JSON string open across a newline: {stripped[:80]!r}"
        )


def test_a_busy_port_is_an_environment_finding() -> None:
    """The composition binds 127.0.0.1:8000.

    A machine already using that port is a condition of the machine. The first
    version reported the resulting bind error as a product failure, after
    spending fifteen minutes on a build it did not need to run.
    """
    script = _script()
    assert "port 8000" in script, "the port must be checked before the build"
    classifier = re.search(
        r'grep -qiE "([^"]*(?:ports are not available|address already in use)[^"]*)"', script
    )
    assert classifier, "a bind failure from compose up is not classified"
    for symptom in ("ports are not available", "address already in use"):
        assert symptom in classifier.group(1)

    # And the pre-flight check must come before the expensive build.
    assert script.index("port 8000") < script.index("--no-cache"), (
        "checking the port after the build wastes the operator's time"
    )


def test_referenced_repository_files_exist() -> None:
    """Same rule as the troubleshooting document: named things must be real."""
    text = _script() + DOC.read_text(encoding="utf-8")
    for path in set(
        re.findall(r"(?:`|\()((?:docs|scripts|frontend)/[A-Za-z0-9_./-]+\.[a-z]+)", text)
    ):
        assert (ROOT / path).exists(), f"referenced path does not exist: {path}"

    assert (ROOT / "compose.yaml").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "frontend" / "package-lock.json").is_file()


def test_the_procedure_bounds_what_a_pass_means() -> None:
    """One green run on one machine is not a portability claim."""
    doc = DOC.read_text(encoding="utf-8")
    assert "not a substitute for CI" in doc or "not a substitute" in doc
    assert re.search(r"one machine|One passing run", doc)
    assert "ASSURANCE.md" in doc, "the assurance boundary must not be implied to have moved"

"""Guards on the operator troubleshooting document.

Three properties, none of which is about whether the prose is good:

  - it does not restate per-code remediation guidance, which has a tested source
    of truth and would drift here;
  - it does not claim that following it fixes anything;
  - the commands, paths, endpoints, and files it names actually exist.

The third is the one that rots silently. A troubleshooting document that tells an
operator to run something that no longer exists is worse than no document, and it
fails in exactly the situation where the reader has least ability to tell.
"""

from __future__ import annotations

import re

from nornyx_lab.academy.pedagogy import PedagogyRepository
from nornyx_lab.engine import repo_root

ROOT = repo_root()
DOC = ROOT / "docs" / "TROUBLESHOOTING.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_document_exists_and_is_linked() -> None:
    assert DOC.is_file()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/TROUBLESHOOTING.md" in readme, "the document is unreachable from the README"


# ------------------------------------------------------- no duplication (1)
def test_no_registered_diagnostic_code_is_troubleshot_here() -> None:
    """Per-code guidance has one home, and it is the tested registry.

    A second copy in prose cannot be checked for outcome claims, cannot be kept
    in step with the codes the academy actually emits, and would win arguments
    it should lose because it is easier to find.
    """
    text = _text()
    codes = {entry.code for entry in PedagogyRepository().remediation().entries}

    # The document may *name* codes as examples of what it does not cover. What
    # it may not do is reproduce their guidance, so look for a code followed by
    # the shape of an explanation rather than for the code alone.
    offenders = []
    for code in sorted(codes):
        for match in re.finditer(re.escape(code), text):
            window = text[match.end() : match.end() + 400]
            if re.search(r"\*\*(Likely cause|Inspect|Try|Verify)\.\*\*", window):
                offenders.append(code)
                break

    assert not offenders, (
        f"these diagnostic codes are troubleshot in TROUBLESHOOTING.md instead of the "
        f"remediation registry: {offenders}"
    )


def test_the_document_points_at_the_in_product_guidance() -> None:
    text = _text()
    assert "/api/v1/remediation" in text
    assert re.search(r"diagnostic code.*stop reading", text, re.IGNORECASE | re.DOTALL)


# ----------------------------------------------------- no outcome claims (2)
def test_no_unsupported_success_claims() -> None:
    """Same rule as the remediation registry, for the same reason."""
    banned = re.compile(
        r"\b("
        r"(this|that|it)\s+(fixes|resolves|solves|corrects)"
        r"|will\s+(fix|resolve|solve|prevent|ensure|guarantee)"
        r"|is\s+now\s+(safe|fixed|resolved|secure|correct)"
        r"|(guarantees|ensures)\s+that"
        r"|problem\s+solved"
        r"|no\s+longer\s+(a\s+)?(risk|an?\s+issue)"
        r")\b",
        re.IGNORECASE,
    )
    hit = banned.search(_text())
    assert not hit, f"TROUBLESHOOTING.md claims an outcome: {hit.group(0)!r}"


def test_every_symptom_section_ends_in_a_verification_step() -> None:
    """A correction without a check is an instruction, which is what this
    document is trying not to be."""
    text = _text()
    corrections = len(re.findall(r"\*\*Try\.\*\*", text))
    verifications = len(re.findall(r"\*\*Verify\.\*\*", text))
    assert corrections >= 8, "the document has too few worked symptoms to be useful"
    assert verifications >= corrections, (
        f"{corrections} corrections but only {verifications} verification steps — "
        f"every 'Try' needs a way to check it"
    )


# --------------------------------------------------- referenced things exist (3)
def test_every_referenced_repository_path_exists() -> None:
    """Paths are quoted in backticks; the ones that look like repository paths
    must resolve."""
    text = _text()
    # Only strings that actually look like paths — a bare `package.json` in
    # prose names a kind of file, not a location in this repository.
    candidates = {
        candidate
        for candidate in re.findall(
            r"`([A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|toml|json|ts|html))`", text
        )
        if "/" in candidate
    }
    # Paths under a runtime-only directory are created by running, not committed.
    ignore_prefixes = ("frontend/dist/", ".nornyx-lab/")
    missing = sorted(
        path
        for path in candidates
        if not path.startswith(ignore_prefixes) and not (ROOT / path).exists()
    )
    assert not missing, f"TROUBLESHOOTING.md references paths that do not exist: {missing}"


def test_every_referenced_script_and_console_command_exists() -> None:
    text = _text()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for script in set(re.findall(r"scripts/([a-z_]+\.py)", text)):
        assert (ROOT / "scripts" / script).is_file(), f"no such script: scripts/{script}"

    for console in set(re.findall(r"\b(nornyx-academy|nornyx-lab)\b", text)):
        assert f"{console} =" in pyproject, f"{console} is not a declared console script"

    for npm_script in set(re.findall(r"npm --prefix frontend run ([a-z:]+)", text)):
        package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        assert f'"{npm_script}"' in package, f"no such npm script: {npm_script}"


def test_every_referenced_api_endpoint_is_served() -> None:
    """An endpoint named here must exist in the application's route table."""
    from nornyx_lab.academy.app import create_app

    text = _text()
    referenced = set(re.findall(r"(/api/v1/[a-z0-9/_-]+)", text))
    served = {getattr(route, "path", "") for route in create_app().routes}
    # Served routes are templated (`/api/v1/modules/{module_id}/run`), while the
    # document names concrete ones (`/api/v1/modules/03/run`), so match a
    # documented path against each template with its parameters widened.
    patterns = [
        re.compile(
            "^" + "[^/]+".join(re.escape(part) for part in re.split(r"\{[^}]+\}", route)) + "$"
        )
        for route in served
        if route.startswith("/api/")
    ]
    missing = sorted(
        path for path in referenced if not any(pattern.match(path) for pattern in patterns)
    )
    assert not missing, f"TROUBLESHOOTING.md names endpoints the app does not serve: {missing}"


def test_environment_variables_named_here_are_read_by_the_application() -> None:
    text = _text()
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src" / "nornyx_lab").rglob("*.py")
    )
    for variable in set(re.findall(r"\b(NORNYX_ACADEMY_[A-Z_]+)\b", text)):
        assert variable in sources, f"{variable} is documented but never read"


def test_docker_facts_match_the_compose_file() -> None:
    """The document makes specific claims about the container boundary."""
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    text = _text()

    assert "compose.yaml" in text, "the document must name the real compose file"
    assert "docker-compose.yml" not in text, "there is no docker-compose.yml in this repository"

    # Claims the document makes, each checked against the file it describes.
    assert "academy:" in compose
    assert "127.0.0.1:8000:8000" in compose and "127.0.0.1:8000:8000" in text
    assert "academy-progress" in compose and "academy-progress" in text
    assert "/app/.nornyx-lab" in compose and "/app/.nornyx-lab" in text
    assert "read_only: true" in compose
    assert "no-new-privileges" in compose


def test_the_playwright_worker_claim_matches_the_config() -> None:
    """The document explains *why* the suite is single-worker. If that ever
    changes, the explanation becomes actively misleading."""
    config = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "workers: 1" in config
    assert "workers: 1" in _text()

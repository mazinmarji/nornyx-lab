#!/usr/bin/env bash
#
# Independent deployment verification for Nornyx Lab.
#
# Answers one question: can a person on a clean, independent machine obtain,
# build, start and use this product by following the documented path, without
# anything peculiar to a development machine?
#
# Two rules make the answer worth having:
#
#   1. This script never installs a prerequisite. If Docker, DNS, TLS trust,
#      or a package registry is unreachable, that is recorded as an ENVIRONMENT
#      failure and the run stops. A script that repairs the machine and then
#      reports success has proved only that it can repair machines.
#
#   2. A PRODUCT failure and an ENVIRONMENT failure are reported separately.
#      "The image would not build because npm could not resolve the registry"
#      and "the governed path failed to prevent the publish" are different
#      findings, and collapsing them would let an infrastructure problem read as
#      a defect, or the reverse.
#
# Prerequisites, in two kinds that must not be confused:
#
#   PRODUCT      docker, docker compose v2 — what the documentation asks an
#                operator to install in order to run Nornyx Lab.
#   HARNESS      bash, git, curl — what *this script* needs to execute. They are
#                checked up front and reported as harness prerequisites, never
#                as product ones.
#
# Deliberately NOT required on the host: python, node, npm, uv, nornyx. Anything
# needing a Python runtime runs inside the already-built production image. A
# verifier that quietly required a host toolchain would be the very portability
# dependency it exists to detect.
#
# Usage:
#   ./scripts/verify_independent_deployment.sh [--evidence DIR] [--keep-running]
#
# Exit status:
#   0  every condition met
#   1  a product condition was not met
#   2  the environment could not support the documented path
#   3  the script was used incorrectly

set -o pipefail

EVIDENCE_DIR="${PWD}/verification-evidence"
KEEP_RUNNING=0
BASE_URL="http://127.0.0.1:8000"
IMAGE_TAG="nornyx-academy:2.0.0"
HEALTH_TIMEOUT=300
PRODUCT_FAILURES=0
ENVIRONMENT_FAILURES=0
STEP=0

while [ $# -gt 0 ]; do
  case "$1" in
    --evidence) EVIDENCE_DIR="$2"; shift 2 ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 3 ;;
  esac
done

mkdir -p "$EVIDENCE_DIR" || { echo "cannot write evidence to $EVIDENCE_DIR" >&2; exit 3; }
LOG="${EVIDENCE_DIR}/verification.log"
: > "$LOG"

say()  { printf '%s\n' "$*" | tee -a "$LOG"; }
head_() { STEP=$((STEP + 1)); say ""; say "── ${STEP}. $* ────────────────────────────────"; }
pass() { say "   PASS  $*"; }
fail() { say "   FAIL  $*"; PRODUCT_FAILURES=$((PRODUCT_FAILURES + 1)); }
envfail() { say "   ENV   $*"; ENVIRONMENT_FAILURES=$((ENVIRONMENT_FAILURES + 1)); }

# Capture a command's output as evidence and report whether it succeeded.
record() {
  local name="$1"; shift
  if "$@" > "${EVIDENCE_DIR}/${name}.txt" 2>&1; then
    return 0
  fi
  return 1
}

# Written from the EXIT trap so that *every* termination path leaves a verdict.
# The procedure tells an operator to keep verdict.json; a run that stops early
# and produces none leaves them with evidence they cannot interpret.
write_verdict() {
  local verdict="pass"
  if [ "$ENVIRONMENT_FAILURES" -gt 0 ]; then
    verdict="environment-failure"
  elif [ "$PRODUCT_FAILURES" -gt 0 ]; then
    verdict="product-failure"
  fi
  {
    echo "{"
    echo "  \"verdict\": \"${verdict}\","
    echo "  \"repository_sha\": \"${REPO_SHA:-unknown}\","
    echo "  \"product_failures\": ${PRODUCT_FAILURES},"
    echo "  \"environment_failures\": ${ENVIRONMENT_FAILURES},"
    echo "  \"reached_step\": ${STEP},"
    echo "  \"image\": \"${IMAGE_TAG}\","
    echo "  \"build_seconds\": ${BUILD_SECONDS:-null},"
    echo "  \"finished_utc\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    # One line: a raw newline inside a JSON string makes the file unparseable,
    # and this is the file the procedure tells an operator to attach.
    echo "  \"note\": \"Verifies the documented deployment path on this machine. It does not revalidate the governance semantics CI already tests, and it never installs a prerequisite: an unmet prerequisite is reported as an environment failure.\""
    echo "}"
  } > "${EVIDENCE_DIR}/verdict.json"
}

cleanup() {
  write_verdict
  if [ "$KEEP_RUNNING" -eq 1 ]; then
    say ""
    say "Composition left running at ${BASE_URL} (--keep-running)."
    return
  fi
  say ""
  say "Tearing down the composition."
  docker compose down -v >> "$LOG" 2>&1 || true
}
trap cleanup EXIT

say "Nornyx Lab — independent deployment verification"
say "Started $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "Evidence: ${EVIDENCE_DIR}"

# ─────────────────────────────────────────────── 1. environment, recorded
head_ "Record the machine"

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "uname=$(uname -a 2>/dev/null || echo unavailable)"
  echo "os=$(uname -s 2>/dev/null || echo unknown)"
  echo "arch=$(uname -m 2>/dev/null || echo unknown)"
  echo "docker=$(docker --version 2>/dev/null || echo MISSING)"
  echo "docker_compose=$(docker compose version 2>/dev/null | head -1 || echo MISSING)"
  # Recorded for context only. The harness never uses a host Python.
  echo "host_python_present_but_unused=$(command -v python3 > /dev/null 2>&1 || command -v python > /dev/null 2>&1 && echo yes || echo no)"
  echo "node=$(node --version 2>/dev/null || echo MISSING)"
  echo "npm=$(npm --version 2>/dev/null || echo MISSING)"
  echo "git=$(git --version 2>/dev/null || echo MISSING)"
  echo "repository_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "repository_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "repository_dirty=$([ -n "$(git status --porcelain 2>/dev/null)" ] && echo yes || echo no)"
} > "${EVIDENCE_DIR}/environment.txt"
cat "${EVIDENCE_DIR}/environment.txt" | tee -a "$LOG" > /dev/null
say "   recorded to environment.txt"

REPO_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
say "   repository at ${REPO_SHA}"

# ─────────────────────────────────────────────── 2. prerequisites, never installed
head_ "Check prerequisites (never installing them)"

if ! command -v docker > /dev/null 2>&1; then
  envfail "docker is not installed. Install it and re-run; this script will not."
elif ! docker info > /dev/null 2>&1; then
  envfail "the docker daemon is not reachable. Start Docker and re-run."
else
  pass "docker is installed and its daemon is reachable"
fi

if ! docker compose version > /dev/null 2>&1; then
  envfail "docker compose (v2) is unavailable; the documented path uses it"
else
  pass "docker compose is available"
fi

if [ ! -f compose.yaml ] || [ ! -f Dockerfile ]; then
  envfail "run this from the repository root: compose.yaml and Dockerfile not found here"
fi

# Harness prerequisites. Checked here, before the fifteen-minute build, and
# named as this script's own needs — so an operator who installed exactly what
# the documentation asked for is never told afterwards to install something else.
for tool in curl git; do
  if ! command -v "$tool" > /dev/null 2>&1; then
    envfail "${tool} is required by this verification script, not by the product."
    envfail "install ${tool} and re-run; the script will not install it."
  else
    pass "${tool} is available (verification harness prerequisite)"
  fi
done

# The composition binds 127.0.0.1:8000. Something already holding that port is a
# condition of this machine, not a defect in the product, and catching it here
# beats a daemon bind error twenty minutes into a build. Probed with bash's own
# /dev/tcp so the check adds no dependency of its own.
if (exec 3<>/dev/tcp/127.0.0.1/8000) 2>/dev/null; then
  exec 3<&- 3>&- 2>/dev/null || true
  envfail "port 8000 on this machine is already in use; free it before verifying"
else
  pass "port 8000 is free for the composition to bind"
fi

if [ "$ENVIRONMENT_FAILURES" -gt 0 ]; then
  say ""
  say "STOPPING: the environment cannot support the documented path."
  say "This is not a finding about the product."
  exit 2
fi

# ─────────────────────────────────────────────── 3. the committed lockfile
head_ "Check the frontend lockfile the documented build depends on"

if [ ! -f frontend/package-lock.json ]; then
  fail "frontend/package-lock.json is missing; the documented build cannot be reproducible"
else
  LOCK_PACKAGES=$(grep -c '"resolved"' frontend/package-lock.json 2>/dev/null || echo 0)
  pass "package-lock.json present (${LOCK_PACKAGES} resolved entries)"
  cp frontend/package-lock.json "${EVIDENCE_DIR}/package-lock.snapshot.json" 2>/dev/null || true
fi

# ─────────────────────────────────────────────── 4. build with no useful cache
head_ "Build the production image from scratch (--no-cache)"

say "   this exercises the documented build, including npm ci against the lockfile"
say "   and the Python dependency resolution, with no local cache to hide a failure"

BUILD_START=$(date +%s)
if record docker-build docker build --no-cache --pull --tag "$IMAGE_TAG" .; then
  BUILD_SECONDS=$(( $(date +%s) - BUILD_START ))
  pass "image built in ${BUILD_SECONDS}s (log: docker-build.txt)"
else
  BUILD_SECONDS=$(( $(date +%s) - BUILD_START ))
  # Distinguish "the network could not supply dependencies" from "the build is broken".
  if grep -qiE "certificate|self.signed|UNABLE_TO_VERIFY|ECONNRESET|ETIMEDOUT|Temporary failure in name resolution|could not resolve host|network timeout|proxy" "${EVIDENCE_DIR}/docker-build.txt"; then
    envfail "the build could not reach a package registry (see docker-build.txt)."
    envfail "this machine cannot fetch dependencies; that is an environment finding, not a defect."
    say ""
    say "STOPPING after ${BUILD_SECONDS}s."
    exit 2
  fi
  fail "the documented docker build failed after ${BUILD_SECONDS}s (see docker-build.txt)"
  exit 1
fi

# ─────────────────────────────────────────────── 5. launch
head_ "Start the documented composition"

if record docker-compose-up docker compose up -d --no-build; then
  pass "composition started"
else
  if grep -qiE "ports are not available|address already in use|bind: |port is already allocated"        "${EVIDENCE_DIR}/docker-compose-up.txt"; then
    envfail "the composition could not bind its port (see docker-compose-up.txt)."
    envfail "another process on this machine holds it; that is an environment finding."
    exit 2
  fi
  fail "docker compose up failed (see docker-compose-up.txt)"
  exit 1
fi

docker compose ps > "${EVIDENCE_DIR}/compose-ps.txt" 2>&1 || true

# ─────────────────────────────────────────────── 6. wait for health, do not sleep
head_ "Wait for the service to report healthy"

say "   polling ${BASE_URL}/api/v1/health (up to ${HEALTH_TIMEOUT}s)"
HEALTHY=0
WAITED=0
while [ "$WAITED" -lt "$HEALTH_TIMEOUT" ]; do
  if curl -fsS --max-time 5 "${BASE_URL}/api/v1/health" > "${EVIDENCE_DIR}/health.json" 2>/dev/null; then
    HEALTHY=1
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
done

if [ "$HEALTHY" -eq 1 ]; then
  pass "healthy after ${WAITED}s: $(cat "${EVIDENCE_DIR}/health.json")"
else
  fail "no health response within ${HEALTH_TIMEOUT}s"
  docker compose logs --no-color --tail=200 > "${EVIDENCE_DIR}/container-logs.txt" 2>&1 || true
  exit 1
fi

if ! grep -q '"status":"ok"' "${EVIDENCE_DIR}/health.json"; then
  fail "health endpoint answered but did not report ok"
fi

# ─────────────────────────────────────────────── 7. the browser client
head_ "Verify the browser client is served, not just the API"

if curl -fsS --max-time 15 "$BASE_URL/" -o "${EVIDENCE_DIR}/index.html" 2>/dev/null; then
  if grep -q 'id="root"' "${EVIDENCE_DIR}/index.html"; then
    pass "the single-page application shell is served from the same origin"
  else
    fail "GET / returned a document without the application root element"
  fi
else
  fail "GET / did not return a document. A healthy API with no page usually means"
  fail "the frontend bundle is absent from the image (see docs/TROUBLESHOOTING.md)"
fi

# ─────────────────────────────────────────────── 8. the five-minute path
head_ "Run the governed and ungoverned paths through the running service"

DEMO_PAYLOAD='{"injection_enabled":true,"enforcement_enabled":true,"enforcement_failure":false,"failure_mode":"fail_closed","identity_ref":"identity.research_assistant","observed_subject_revision":null,"approval_state":"missing","planner_mode":"deterministic"}'

if curl -fsS --max-time 180 -X POST "${BASE_URL}/api/v1/demo/run" \
     -H "Content-Type: application/json" -d "$DEMO_PAYLOAD" \
     -o "${EVIDENCE_DIR}/demo-run.json" 2>/dev/null; then
  pass "the scenario executed inside the production container"
else
  fail "the demo endpoint did not return a result"
  docker compose logs --no-color --tail=200 > "${EVIDENCE_DIR}/container-logs.txt" 2>&1 || true
  exit 1
fi

# ─────────────────────────────────────────────── 9. the semantics, not just a 200
head_ "Require the expected counter semantics"

# Parsed by the Python inside the production image, piped over stdin. The host
# needs no interpreter: requiring one would make this script the hidden
# portability dependency it exists to find.
if docker run --rm -i --entrypoint python "$IMAGE_TAG" -c '
import json, sys

run = json.load(sys.stdin)
variants = {v["id"]: v for v in run["variants"]}
problems = []

def publication(variant):
    for counter in variants[variant]["counters"]:
        if counter["action"] == "publish_external":
            return counter
    return None

ungoverned = publication("ungoverned")
governed = publication("governed")

if ungoverned is None or governed is None:
    print("no publish_external counter on one of the paths")
    raise SystemExit(1)

print(f"ungoverned publish_external: {ungoverned['attempts']}/{ungoverned['completions']} "
      f"({ungoverned['meaning']})")
print(f"governed   publish_external: {governed['attempts']}/{governed['completions']} "
      f"({governed['meaning']})")

# The ungoverned path must show the tool actually ran.
if (ungoverned["attempts"], ungoverned["completions"]) != (1, 1):
    problems.append("ungoverned path did not record 1 attempt and 1 completion")
if ungoverned["meaning"] != "executed":
    problems.append(f"ungoverned meaning is {ungoverned['meaning']!r}, expected 'executed'")

# The governed path must show 0/0 -- AND that 0/0 means prevention here, which
# it only does because the same plan demonstrably reached the tool without
# governance. A 0/0 with nothing planned would prove nothing at all.
if (governed["attempts"], governed["completions"]) != (0, 0):
    problems.append("governed path did not record 0 attempts and 0 completions")
if governed["meaning"] != "prevented_before_execution":
    problems.append(
        f"governed meaning is {governed['meaning']!r}; 0/0 counts as prevention only when "
        f"the action was actually planned"
    )
if not problems:
    print("0/0 is interpretable as prevention: the same plan recorded 1/1 without governance")

for problem in problems:
    print(f"PROBLEM: {problem}")
raise SystemExit(1 if problems else 0)
' < "${EVIDENCE_DIR}/demo-run.json" > "${EVIDENCE_DIR}/counter-check.txt" 2>&1
then
  while IFS= read -r line; do say "   $line"; done < "${EVIDENCE_DIR}/counter-check.txt"
  pass "counter semantics are as documented"
else
  while IFS= read -r line; do say "   $line"; done < "${EVIDENCE_DIR}/counter-check.txt"
  fail "the counter semantics the product documents were not observed"
fi

# ─────────────────────────────────────────── 10. persistence across restart
head_ "Verify progress persists across a restart (the composition promises a volume)"

curl -fsS --max-time 30 "${BASE_URL}/api/v1/progress" -o "${EVIDENCE_DIR}/progress-before.json" 2>/dev/null || true

if record docker-restart docker compose restart; then
  RESTART_OK=0
  WAITED=0
  while [ "$WAITED" -lt "$HEALTH_TIMEOUT" ]; do
    if curl -fsS --max-time 5 "${BASE_URL}/api/v1/health" > /dev/null 2>&1; then
      RESTART_OK=1
      break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
  done

  if [ "$RESTART_OK" -eq 1 ]; then
    curl -fsS --max-time 30 "${BASE_URL}/api/v1/progress" -o "${EVIDENCE_DIR}/progress-after.json" 2>/dev/null || true
    # Both payloads stream in as one JSON array, so the container needs no
    # mounted path and the host still needs no interpreter.
    if { echo "["; cat "${EVIDENCE_DIR}/progress-before.json"; echo ",";          cat "${EVIDENCE_DIR}/progress-after.json"; echo "]"; }        | docker run --rm -i --entrypoint python "$IMAGE_TAG" -c '
import json, sys
before, after = json.load(sys.stdin)
def executions(payload):
    return {m["module_id"]: m.get("executions", 0) for m in payload.get("modules", [])}
b, a = executions(before), executions(after)
if not b:
    print("no learner record before restart; nothing to compare")
    raise SystemExit(1)
lost = [k for k, v in b.items() if a.get(k, 0) < v]
print("modules with fewer executions after restart:", lost or "none")
raise SystemExit(1 if lost else 0)
' >> "$LOG" 2>&1
    then
      pass "the learner record survived the restart"
    else
      fail "progress did not survive a restart, though the composition mounts a named volume"
    fi
  else
    fail "the service did not come back healthy after restart"
  fi
else
  fail "docker compose restart failed"
fi

# ─────────────────────────────────────────────── 11. evidence and verdict
head_ "Write the verdict"

docker compose logs --no-color --tail=300 > "${EVIDENCE_DIR}/container-logs.txt" 2>&1 || true
docker image inspect "$IMAGE_TAG" > "${EVIDENCE_DIR}/image-inspect.json" 2>&1 || true

VERDICT="pass"
EXIT_CODE=0
if [ "$ENVIRONMENT_FAILURES" -gt 0 ]; then
  VERDICT="environment-failure"
  EXIT_CODE=2
elif [ "$PRODUCT_FAILURES" -gt 0 ]; then
  VERDICT="product-failure"
  EXIT_CODE=1
fi

say ""
say "════════════════════════════════════════════════"
say " Verdict: ${VERDICT}"
say " Product failures: ${PRODUCT_FAILURES}   Environment failures: ${ENVIRONMENT_FAILURES}"
say " Repository: ${REPO_SHA}"
say " Evidence:   ${EVIDENCE_DIR}"
say "════════════════════════════════════════════════"

exit "$EXIT_CODE"

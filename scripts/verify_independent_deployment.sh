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
#   4  the verification instrument itself failed; this run says nothing about
#      the product, and must not be read as a product judgement

set -o pipefail

EVIDENCE_DIR="${PWD}/verification-evidence"
KEEP_RUNNING=0
BASE_URL="http://127.0.0.1:8000"
IMAGE_TAG="nornyx-academy:2.0.0"
# Overridable so a harness test can bound the wait; an operator never needs to.
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
PRODUCT_FAILURES=0
ENVIRONMENT_FAILURES=0
# A fault in the instrument itself. Kept apart from both other kinds: it is not
# a statement about the product, and it is not a limitation of the machine.
VERIFIER_FAILURES=0
STEP=0
# Set only after the final verification step. Absent it, the run did not finish,
# and an unfinished run must never be able to report `pass` — a SIGTERM or an
# external timeout would otherwise leave false acceptance evidence behind.
COMPLETED=0
# Set only after *this* invocation brings the composition up. The teardown is
# gated on it, so a run that stopped at the preflight cannot destroy a
# deployment, or a progress volume, that it never created.
COMPOSITION_STARTED=0

while [ $# -gt 0 ]; do
  case "$1" in
    --evidence)
      # A bare `--evidence` must be a usage error, not an empty assignment that
      # silently writes evidence somewhere unexpected or spins on an argument
      # that is not there.
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "--evidence requires a directory" >&2
        exit 3
      fi
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 3 ;;
  esac
done

# Read the repository's state *before* creating any evidence file. Writing the
# log first would make a pristine checkout look dirty — the verifier
# contaminating the very condition it is trying to record.
REPO_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
REPO_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
REPO_DIRTY="$([ -n "$(git status --porcelain 2>/dev/null)" ] && echo yes || echo no)"

mkdir -p "$EVIDENCE_DIR" || { echo "cannot write evidence to $EVIDENCE_DIR" >&2; exit 3; }
LOG="${EVIDENCE_DIR}/verification.log"
: > "$LOG"

say()  { printf '%s\n' "$*" | tee -a "$LOG"; }
head_() { STEP=$((STEP + 1)); say ""; say "── ${STEP}. $* ────────────────────────────────"; }
pass() { say "   PASS  $*"; }
fail() { say "   FAIL  $*"; PRODUCT_FAILURES=$((PRODUCT_FAILURES + 1)); }
envfail() { say "   ENV   $*"; ENVIRONMENT_FAILURES=$((ENVIRONMENT_FAILURES + 1)); }
verifierfail() { say "   BUG   $*"; VERIFIER_FAILURES=$((VERIFIER_FAILURES + 1)); }

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
  # `pass` is earned, never defaulted. A run killed by a signal or an external
  # timeout reaches this trap with both counters at zero; reporting that as a
  # pass would be false acceptance evidence, which is worse than none.
  local verdict="incomplete"
  if [ "$VERIFIER_FAILURES" -gt 0 ]; then
    # Ranked first: if the instrument failed, no other reading of this run is
    # trustworthy, and the result must not be presented as a product judgement.
    verdict="verifier-failure"
  elif [ "$ENVIRONMENT_FAILURES" -gt 0 ]; then
    verdict="environment-failure"
  elif [ "$PRODUCT_FAILURES" -gt 0 ]; then
    verdict="product-failure"
  elif [ "$COMPLETED" -eq 1 ]; then
    verdict="pass"
  fi
  {
    echo "{"
    echo "  \"verdict\": \"${verdict}\","
    echo "  \"repository_sha\": \"${REPO_SHA:-unknown}\","
    echo "  \"product_failures\": ${PRODUCT_FAILURES},"
    echo "  \"environment_failures\": ${ENVIRONMENT_FAILURES},"
    echo "  \"verifier_failures\": ${VERIFIER_FAILURES},"
    echo "  \"reached_step\": ${STEP},"
    echo "  \"completed\": $([ "$COMPLETED" -eq 1 ] && echo true || echo false),"
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
  if [ "$COMPOSITION_STARTED" -ne 1 ]; then
    # Nothing was started here, so there is nothing of ours to remove. This
    # matters most in the case the preflight exists to catch: port 8000 already
    # held by an earlier run, where an unconditional `down -v` would stop that
    # deployment and delete its progress volume.
    return
  fi
  if [ "$KEEP_RUNNING" -eq 1 ]; then
    say ""
    say "Composition left running at ${BASE_URL} (--keep-running)."
    return
  fi
  say ""
  say "Tearing down the composition this run started."
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
  # Captured before any evidence file existed; see above.
  echo "repository_sha=${REPO_SHA}"
  echo "repository_branch=${REPO_BRANCH}"
  echo "repository_dirty=${REPO_DIRTY}"
} > "${EVIDENCE_DIR}/environment.txt"
cat "${EVIDENCE_DIR}/environment.txt" | tee -a "$LOG" > /dev/null
say "   recorded to environment.txt"

say "   repository at ${REPO_SHA} (dirty: ${REPO_DIRTY})"

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
  COMPOSITION_STARTED=1
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

# Run as a packaged module, never as a shell string.
#
# This check used to be a Python program embedded in `python -c '…'`. Its
# dictionary keys were single-quoted inside a single-quoted shell argument, so
# bash removed the inner quotes and Python received `counter[attempts]`. The
# first independent run died here with NameError — and the harness called that a
# product failure. A module cannot be rewritten by the shell on its way to the
# interpreter, and it is syntax-checked and unit-tested like any other code.
docker run --rm -i --entrypoint python "$IMAGE_TAG"   -m nornyx_lab.verification.check_counters   < "${EVIDENCE_DIR}/demo-run.json" > "${EVIDENCE_DIR}/counter-check.txt" 2>&1
COUNTER_STATUS=$?

if [ "$COUNTER_STATUS" -eq 0 ];
then
  while IFS= read -r line; do say "   $line"; done < "${EVIDENCE_DIR}/counter-check.txt"
  pass "counter semantics are as documented"
elif [ "$COUNTER_STATUS" -eq 4 ]; then
  # The checker could not decide. That says nothing about the product, and
  # recording it as a product failure would attribute a defect to the thing
  # being measured — which is exactly what the first independent run did.
  while IFS= read -r line; do say "   $line"; done < "${EVIDENCE_DIR}/counter-check.txt"
  verifierfail "the semantic checker could not complete (see counter-check.txt)"
  verifierfail "this is a fault in the verification instrument, not evidence about the product"
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
    # mounted path and the host still needs no interpreter. Packaged module, not
    # an inline program: see check_counters for why that distinction cost a run.
    { echo "["; cat "${EVIDENCE_DIR}/progress-before.json"; echo ",";       cat "${EVIDENCE_DIR}/progress-after.json"; echo "]"; }        | docker run --rm -i --entrypoint python "$IMAGE_TAG"            -m nornyx_lab.verification.check_persistence >> "$LOG" 2>&1
    PERSISTENCE_STATUS=$?

    if [ "$PERSISTENCE_STATUS" -eq 0 ]; then
      pass "the learner record survived the restart"
    elif [ "$PERSISTENCE_STATUS" -eq 4 ]; then
      # Same rule as step 9: a checker that cannot decide is not evidence that
      # the product lost data.
      verifierfail "the persistence checker could not complete (see verification.log)"
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

# Every verification step has now run. Only from here can the verdict be pass.
COMPLETED=1

VERDICT="pass"
EXIT_CODE=0
if [ "$VERIFIER_FAILURES" -gt 0 ]; then
  VERDICT="verifier-failure"
  EXIT_CODE=4
elif [ "$ENVIRONMENT_FAILURES" -gt 0 ]; then
  VERDICT="environment-failure"
  EXIT_CODE=2
elif [ "$PRODUCT_FAILURES" -gt 0 ]; then
  VERDICT="product-failure"
  EXIT_CODE=1
fi

say ""
say "════════════════════════════════════════════════"
say " Verdict: ${VERDICT}"
say " Product failures: ${PRODUCT_FAILURES}   Environment: ${ENVIRONMENT_FAILURES}   Verifier: ${VERIFIER_FAILURES}"
say " Repository: ${REPO_SHA}"
say " Evidence:   ${EVIDENCE_DIR}"
say "════════════════════════════════════════════════"

exit "$EXIT_CODE"

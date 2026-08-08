# Operator troubleshooting and known limitations

For the person who **runs** the academy, not the person learning in it.

Every entry follows the same shape, for the same reason the lessons do:

> symptom → likely cause → what to inspect → a correction to try → **how to verify**

The last step is not decoration. Following a suggestion here is not evidence that
it worked; running the check afterwards is. Nothing in this document should be
read as "do this and you are done".

## If the browser shows a diagnostic code, stop reading this document

Codes such as `CAPABILITY_DENIED`, `AN_LOCK_SOURCE_STALE`, or
`EVIDENCE_BINDING_REFUSED` are **not** troubleshot here. Each one carries its own
guidance in the product, next to the diagnostic itself: expand
**"What this means, and what to check"** under the finding.

That guidance is a tested registry served from `/api/v1/remediation`, and it is
deliberately the single source of truth for per-code meaning. Copying any of it
into this file would create a second, unverified version that drifts. This
document covers only failures that never produce a diagnostic code — the ones
that happen before, or outside, the governance model.

---

## 1. The application will not start

### `nornyx-academy: command not found`

**Likely cause.** The console script is installed into the project environment,
and the shell is not using it.

**Inspect.** Whether the environment exists and which interpreter is in use:

```bash
uv run --frozen python -c "import nornyx_lab, sys; print(sys.executable)"
```

**Try.** Create the environment, then invoke through it:

```bash
uv sync --frozen --extra dev --extra crewai --extra langgraph
```

**Verify.** `uv run --frozen nornyx-academy --help` prints the `--host`,
`--port`, and `--reload` options. If it does not, the environment is still not
the one holding the package.

### `ModuleNotFoundError` on start, or an unexpected Nornyx version

**Likely cause.** The environment drifted from the lockfile, or a different
interpreter is active.

**Inspect.** The versions actually loaded, which are pinned exactly and not to a
range:

```bash
uv run --frozen python -c "import nornyx, nornyx_agentic_adapters as a; print(nornyx.__version__, a.__version__)"
```

**Try.** `uv sync --frozen` to restore the locked set. On this project a floating
version is never correct: a pin change would silently alter diagnostic codes and
invalidate lessons.

**Verify.** The command above prints `1.11.0` and `0.3.0`, and
`uv lock --check` exits zero.

### The port is already in use

**Likely cause.** A previous server is still bound to 8000, often one started by
Playwright's `webServer` and left running.

**Inspect.** What holds the port:

```bash
python -c "import socket;s=socket.socket();print('in use' if s.connect_ex(('127.0.0.1',8000))==0 else 'free')"
```

**Try.** Stop the existing process, or bind elsewhere:
`uv run --frozen nornyx-academy --port 8100`.

**Verify.** `curl http://127.0.0.1:<port>/api/v1/health` returns
`{"status":"ok","api_version":"v1"}`.

### The API answers but the browser shows `{"detail":"Not Found"}`

This is the most commonly misread failure, because the service is genuinely
healthy — only the page is missing.

**Likely cause.** `frontend/dist` does not exist, so the single-page application
was never mounted. The API is served regardless; the browser client is not.

**Inspect.** Whether the build output is present:

```bash
python -c "import pathlib;p=pathlib.Path('frontend/dist/index.html');print('present' if p.is_file() else 'MISSING')"
```

**Try.** Build the client (see §2), or point the server at an existing build with
`NORNYX_ACADEMY_FRONTEND_DIST`.

**Verify.** `curl -s http://127.0.0.1:8000/ | head -c 200` contains
`<div id="root">`. A 404 here with a healthy `/api/v1/health` always means the
bundle, never the service.

### The database path cannot be written

**Likely cause.** The default location is not writable by the running user.

**Inspect.** The resolved path — `.nornyx-lab/academy.db` under the repository
root unless `NORNYX_ACADEMY_DB` overrides it.

**Try.** Point it somewhere writable:

```bash
NORNYX_ACADEMY_DB=/tmp/academy.db uv run --frozen nornyx-academy
```

**Verify.** `/api/v1/health` returns ok **and** `/api/v1/progress` returns a
module list. Health alone does not exercise the database.

---

## 2. Frontend and build problems

### `npm ci` or `npm run build` fails

**Likely cause.** Node is older than the project requires, or the lockfile and
`package.json` disagree.

**Inspect.** `node --version` against the declared engine, `>=20.11.0`.

**Try.** Install with scripts disabled, exactly as CI and the Dockerfile do:

```bash
npm --prefix frontend ci --ignore-scripts
```

**Verify.** `frontend/node_modules/.bin/vite` exists and
`npm --prefix frontend run build` writes `frontend/dist/index.html`. If `npm ci`
exits without creating `.bin`, treat it as a network failure and read §3 before
retrying — a partial `node_modules` is the normal symptom of an interrupted
download, not of a corrupt lockfile.

### The browser shows an old version of a page you just changed

**Likely cause.** The server reads `frontend/dist` from disk on every request, so
a stale page is almost always the **browser** caching `index.html`, not the
server holding an old build.

**Inspect.** Compare the asset the page requested with the one on disk:

```bash
curl -s http://127.0.0.1:8000/ | grep -o "assets/index-[A-Za-z0-9_-]*\.js"
ls frontend/dist/assets/
```

**Try.** Rebuild, then load the page with a cache-busting query
(`http://127.0.0.1:8000/demo?cb=1`) or a hard reload.

**Verify.** The hash from the first command appears in the second listing. If
they match and the content still looks old, the build itself did not include the
change — check that the edit was saved in `frontend/src`.

---

## 3. Network, TLS, and proxy problems

### `UNABLE_TO_VERIFY_LEAF_SIGNATURE`, or npm fails with `Exit handler never called!`

**Likely cause.** Something is intercepting HTTPS and presenting its own
certificate — a corporate proxy, or consumer antivirus with HTTPS scanning
enabled. npm reports this misleadingly: `Exit handler never called!` reads like
an npm bug, and the real error appears only in the debug log.

**Inspect.** The actual error, and the certificate chain being presented:

```bash
node -e "const t=require('tls');const s=t.connect({host:'registry.npmjs.org',port:443,servername:'registry.npmjs.org',rejectUnauthorized:false},()=>{let c=s.getPeerCertificate(true);while(c){console.log(c.subject&&c.subject.CN,'<-',c.issuer&&c.issuer.CN);if(c.issuerCertificate===c)break;c=c.issuerCertificate;}s.end();});"
```

The npm debug log named in the failure output holds the underlying error.

**Try.** Point npm at the intercepting root certificate. npm's fetch layer does
**not** honour `NODE_EXTRA_CA_CERTS`; it reads `cafile`:

```bash
npm --prefix frontend ci --ignore-scripts --cafile /path/to/root.pem
```

If TLS then succeeds but connections reset mid-install, reduce concurrency:
`--maxsockets 2 --fetch-retries 8`.

**Verify.** `npm view vite version --cafile /path/to/root.pem` prints a version.
Do this before a full install — it fails in seconds rather than minutes.

### `uv` cannot reach PyPI

**Likely cause.** The same interception, on the Python side.

**Try.** `uv sync --frozen --native-tls`, which uses the platform trust store.

**Verify.** `uv lock --check` exits zero.

---

## 4. Docker problems

The compose file is **`compose.yaml`**, and the service is **`academy`**.

### The image builds but the container is unhealthy

**Likely cause.** The health check polls the API inside the container; it fails
while the application is still starting, or if the process died.

**Inspect.**

```bash
docker compose ps
docker compose logs academy
```

**Try.** Give it the full start period — the check allows 15s before counting
failures, then retries every 30s — and read the logs rather than restarting
blindly.

**Verify.** `docker compose ps` reports `healthy`, and
`curl http://127.0.0.1:8000/api/v1/health` answers from the host.

### The build fails downloading a dependency

**Likely cause.** A slow or intercepted network inside the build. Large wheels
are the usual casualty, and `uv`'s default HTTP timeout is short.

**Inspect.** The failing package named in the build output.

**Try.** Raise the timeout for the build, for example by passing
`UV_HTTP_TIMEOUT` into the build environment, or build on a network without
interception.

**Verify.** `docker build --tag nornyx-academy:2.0.0 .` completes, and
`docker compose up -d` reaches `healthy`.

### The container cannot write

**Likely cause.** This is deliberate, not a fault. The container runs read-only,
as a non-root user, with all Linux capabilities dropped and
`no-new-privileges`. Only two locations are writable: the `academy-progress`
volume mounted at `/app/.nornyx-lab`, and a `tmpfs` at `/tmp`.

**Inspect.** Whether the path being written is one of those two.

**Try.** Write learner state under `/app/.nornyx-lab`. Do not relax `read_only`
to make an unrelated write succeed — that removes a real boundary to work around
a symptom.

**Verify.** Progress survives `docker compose restart`, which exercises the
volume rather than the container filesystem.

### The port is not reachable from another machine

**Likely cause.** Also deliberate. The published port is bound to
`127.0.0.1:8000:8000`, so it is reachable from the host only.

**Try.** If remote access is genuinely wanted, change the binding consciously and
put an authenticating proxy in front. The academy has no authentication of its
own and is not built to be exposed.

**Verify.** From the host, `curl http://127.0.0.1:8000/api/v1/health`.

---

## 5. Playwright problems

### `browserType.launch: Executable doesn't exist`

**Likely cause.** The browser binary is not installed, or its build number does
not match the installed Playwright package.

**Inspect.** The build number in the error against what is on disk (under
`~/.cache/ms-playwright`, or `%LOCALAPPDATA%\ms-playwright` on Windows).

**Try.** `npx playwright install chromium`. A mismatch is a version difference
between package and browser, not a missing install.

**Verify.** `npx playwright test --list` enumerates the specs without launching.

### Tests fail locally that pass in CI

**Likely cause.** Assertion timeouts on a slower machine. Several assertions
follow a **real** engine execution: a lesson run spawns the Nornyx CLI in an
isolated per-run workspace and takes several seconds. The configuration allows
120s per test and 20s per assertion for exactly this reason.

**Inspect.** How long a single run actually takes here:

```bash
curl -s -o /dev/null -w "%{time_total}s\n" -X POST http://127.0.0.1:8000/api/v1/modules/03/run -H "Content-Type: application/json" -d "{}"
```

**Try.** Run one spec alone to separate a genuine failure from a slow one. If it
passes alone and fails in the suite, suspect timing or shared state rather than
the assertion.

**Verify.** The full suite passes twice in a row. A single green run does not
distinguish a fix from a flake.

### Why the suite runs on one worker

Not a performance oversight. Every test drives the same academy service and the
same learner record, and each begins by posting to `/api/v1/progress/reset`. With
more than one worker, a second test resets the database underneath a journey
already in progress — which surfaces as an unrelated failure in a different spec
file. `workers: 1` is load-bearing; raising it will produce confusing,
intermittent failures.

### The server Playwright starts is not the one you expect

Locally the config reuses an already-running server rather than starting its own.
If a stale server from earlier work is bound to 8000, tests run against **that**
code. Stop it, or set `PLAYWRIGHT_BASE_URL` to target a chosen origin.

---

## 6. Learner state and progress

Progress lives in a single SQLite file: `.nornyx-lab/academy.db` under the
repository root by default, or wherever `NORNYX_ACADEMY_DB` points. Under Docker
it lives in the `academy-progress` volume.

**Safe to delete.** The database itself. It holds only learner progress —
completions, assessment attempts, scores. Deleting it returns the academy to a
fresh state and destroys nothing else. It is not the source of any contract,
artifact, or lock.

**Not safe to delete.** Anything under `contracts/` — the checked `.nyx` sources,
`*.lock` files, `control_artifacts/`, and `governance_evidence/` are committed
outputs owned by `scripts/build_contracts.py`, and the drift gate compares
against them.

**To reset without deleting the file**, use the in-product reset, which the
browser calls: `POST /api/v1/progress/reset`.

For scratch directories the labs create while running, `python scripts/clean.py`
removes them and is documented as never touching committed contract outputs.

**Verify.** After a reset, `/api/v1/progress` reports every module as
`not_started`.

---

## 7. Known limitations

These are boundaries of the product, not defects. Each is deliberate, and each is
something an operator could otherwise mistake for something broken.

### Enforcement is cooperative and in-process (Tier 2)

The scenario engine asks Nornyx for a decision and honours it before entering the
business callable. That is a real control and a bounded one: the acting identity
is asserted rather than authenticated, the approver is a supplied claim, evidence
is produced in the same process as the action, and any code in that process can
call the business function directly and bypass the path entirely.

The curriculum teaches that bypass rather than hiding it. A stronger tier would
need a control the acting process cannot switch off and a witness it does not
own. The academy implements neither and claims neither.

### The academy is not itself governed by Nornyx

No `.nyx` contract authorizes the API service, and no capability check gates
writing a progress record. Shipping a control and self-applying it are different
commitments.

### Business effects are inert

Nothing is published, sent, transferred, or deleted. Actions are recorded in an
in-memory ledger. Counters describe that ledger, not the outside world — which is
precisely why they can be trusted as a measurement of whether software *entered*
the function.

### Planning is deterministic and offline by default

The default planner is a fixture, clearly labelled as a susceptible teaching
device rather than an LLM. This is what makes the governed/ungoverned comparison
reproducible. Enabling the optional live model makes runs non-deterministic; a
different live proposal is never an invariant outcome.

### Optional frameworks may be absent

CrewAI and LangGraph lessons report unavailability explicitly instead of quietly
skipping, because a silent skip is indistinguishable from a pass. Coverage claims
should name only the frameworks that actually ran.

### Evidence integrity is not evidence completeness

Nornyx validates how supplied records were constructed, ordered, and bound. It
does not establish that every relevant event was supplied, and it does not
authenticate the producer. Nothing you can run inside this process settles
completeness.

---

## Related documents

- [Development, deployment, and testing](DEVELOPMENT.md) — the supported
  toolchain and the full gate list
- [Security and sandbox boundary](SECURITY.md)
- [Honest assurance statement](ASSURANCE.md)
- [User guide](USER_GUIDE.md) — for learners rather than operators

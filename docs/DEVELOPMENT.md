# Development, deployment, testing, and upgrades

This guide is for maintainers and operators. Learners should receive the browser URL and the
[user guide](USER_GUIDE.md), not toolchain setup instructions.

## Supported toolchain

| Tool | Project baseline |
|---|---|
| Python | `>=3.10`; CI and the production image use `3.12.11` |
| uv | `0.9.3` in Docker and CI; use a compatible local release that honors `uv.lock` |
| Node.js | `22.18.0` in Docker and CI; package metadata requires at least `20.11.0` |
| npm | The version bundled with the selected Node release; dependencies come from `package-lock.json` |
| Docker | BuildKit-capable engine with Compose v2 |

Application, test, framework, and browser versions are exact in `pyproject.toml`, `uv.lock`,
`frontend/package.json`, and `frontend/package-lock.json`. Do not replace frozen installation with
floating `pip install` or `npm install` in CI or production.

## Source environment

From the repository root, create the complete verified Python environment and browser dependency
tree:

```bash
uv sync --frozen --extra dev --extra crewai --extra langgraph
npm --prefix frontend ci --ignore-scripts
uv run --frozen python scripts/build_contracts.py --verify
```

The framework extras are intentional. They prevent CrewAI and LangGraph lessons from quietly
becoming green skips. Install the optional live-model client only on a source deployment that is
explicitly allowed to make provider requests:

```bash
uv sync --frozen --extra dev --extra crewai --extra langgraph --extra live
```

Never put a provider key in a shell history, environment file, repository file, browser build, or
container image. The supported learner flow submits it from **Settings** to process memory.

## Two-process development

Run the API and Vite as separate processes so Python and React both reload:

```bash
uv run --frozen uvicorn nornyx_lab.academy.app:app --reload --host 127.0.0.1 --port 8000
```

In a second shell:

```bash
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`. To use a different
backend during frontend development, set `VITE_BACKEND_ORIGIN` before starting Vite.

The `make dev` target starts only the backend by design; it prints the companion frontend command
in its help. Direct commands above work on PowerShell as well as POSIX shells.

## Production-style source deployment

Build the static application, then let FastAPI serve it and `/api/v1` from the same origin:

```bash
npm --prefix frontend run build
uv run --frozen nornyx-academy --host 127.0.0.1 --port 8000
```

The production build is `frontend/dist`. If it is absent, API routes still work but browser routes
are not mounted; this is explicit service deployment failure, not a fallback UI. Bind to a
non-loopback interface only inside a trusted network boundary and place normal authentication,
TLS, and reverse-proxy controls in front of any shared deployment. The initial persistence model
is local single-user SQLite, not multi-user tenancy.

## Docker deployment

Build and run the hardened local deployment:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000`. The multi-stage image builds the React client with Node
`22.18.0`, installs the frozen Python runtime on Python `3.12.11`, and runs as a non-root user.
Compose binds only to loopback, drops Linux capabilities, uses `no-new-privileges`, makes the root
filesystem read-only, and provides:

- `academy-progress` for `/app/.nornyx-lab/academy.db`;
- a size-bounded, `noexec`, `nosuid` temporary filesystem for isolated runs.

Stop the service without deleting progress:

```bash
docker compose down
```

`docker compose down --volumes` permanently deletes the local learner volume; use the dashboard’s
export function first and run the volume-removal command only when deletion is intended.

Build the exact production image without starting it:

```bash
docker build --tag nornyx-academy:2.0.0 .
```

## Runtime configuration

| Variable | Purpose |
|---|---|
| `NORNYX_ACADEMY_DB` | SQLite learner-record path. Default: `.nornyx-lab/academy.db` in source and `/app/.nornyx-lab/academy.db` in Docker. |
| `VITE_BACKEND_ORIGIN` | Vite/preview proxy target during frontend development. It is not a production runtime switch. |
| `PLAYWRIGHT_BASE_URL` | Use an already-running deployment instead of Playwright’s managed API/preview servers. |
| `CREWAI_DISABLE_TELEMETRY=true` | Prevent CrewAI first-run tracing initialization. Must exist before import. |
| `CREWAI_TRACING_ENABLED=false` | Disable CrewAI tracing for deterministic guarded tests. Must exist before import. |
| `CREWAI_TESTING=true` | Select CrewAI testing behavior before conformance imports. |
| `OTEL_SDK_DISABLED=true` | Disable OpenTelemetry SDK startup in deterministic training/test processes. |
| `PYTHONIOENCODING=utf-8` | Stabilize subprocess/test output, especially on Windows. |
| `UV_FROZEN=true` | Makes indirect `uv` calls, including Playwright’s managed backend, honor the committed lock in CI. |

`LAB_AS_OF=2026-06-01T12:00:00Z` and
`LAB_SUBJECT_REVISION=git:5eed1e55c0ffee1abadcafe0ddba11ed15ea5e11` are mirrored in CI so the
determinism contract is visible. Their canonical application values are constants in
`src/nornyx_lab/constants.py`; do not turn evaluation back into a wall-clock read. The pinned time
falls within the declared approval interval from 2026-06-01 through 2026-06-08.

## Execution isolation

`run_structured_lab` creates a new temporary workspace for each legacy execution, copies only the
required repository fixtures, redirects dynamic root lookup inside a guarded context, redacts host
paths, and removes the copy after the run. This is required because Labs 11 and 15 deliberately
tamper with generated artifacts and locks.

Never parallelize the original lab suite against the shared checkout. The preserved labs still
have shared mutation assumptions. CI runs the original regression serially, while browser runs
are isolated by construction. New scenarios should prefer immutable definitions and in-memory
inert ledgers; they must not write contracts, artifacts, or progress outside their assigned
boundary.

## Test gates

### Frozen dependencies and contracts

```bash
uv lock --check
uv sync --frozen --extra dev --extra crewai --extra langgraph
git diff --exit-code -- uv.lock
uv run --frozen python scripts/build_contracts.py --verify
```

The contract verifier rebuilds in scratch and byte-compares checked source-derived artifacts and
locks. Any intended source change must be regenerated and reviewed; a hand-edited derived artifact
must fail.

### Fast backend and API suite

```bash
uv run --frozen pytest tests/academy -m "not all_labs" -q -rs
```

This covers catalog integrity, assessments, progress persistence/export/reset, settings-secret
boundaries, API contracts and security headers, deterministic A/B behavior, foundations, contract
explorer/builder equivalence, evidence, capstone behavior, and representative isolated migration.

### Full original regression

```bash
uv run --frozen pytest labs tests/test_repository.py -q -rs
```

Run serially. The baseline is intentionally slow because it executes the real Nornyx toolchain and
all original concept checks. No skip is acceptable when both framework extras are installed.

### All 25 structured browser migrations

```bash
uv run --frozen pytest tests/academy/test_structured.py -m all_labs -q -rs
```

This gate runs every original lab through the temporary-workspace and typed-response boundary and
asserts that source fixtures do not change. CI runs it on Linux and Windows; the full original
regression runs once on Linux to avoid duplicating the most expensive suite across a matrix.

### Adapter conformance

```bash
uv run --frozen python -m nornyx_agentic_adapters.conformance \
  --require crewai --require langgraph \
  --json conformance-report.json --summary
```

`--require` turns an absent framework into failure. The CrewAI environment controls listed above
must be present before import. A “not representable” inventory result is an explicit supported
outcome of the pinned kit; a blocked process, outbound request, credential access, model call, or
missing required framework is not.

### Python style

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

### Frontend component and production-build checks

```bash
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend test
npm --prefix frontend run build
```

Component tests cover API error semantics, claim rendering, counter meaning, evidence/scenario
rendering, and accessible feedback states. TypeScript compilation is part of `npm run build`.

### Browser and accessibility journey

Install Chromium once in the frontend workspace, build, and run Playwright:

```bash
cd frontend
npx playwright install chromium
npm run build
npm run test:e2e
```

Playwright starts a fresh FastAPI service and production preview unless `PLAYWRIGHT_BASE_URL` is
set. The test resets a temporary learner database, opens the product, runs both A/B variants,
asserts `1/1` versus `0/0`, opens evidence, passes assessment, verifies saved completion, runs axe
against the fresh and result states, and writes a screenshot under
`frontend/test-results/visual-evidence`. CI uploads screenshots, traces, and reports even when the
test fails.

### Container gate

```bash
docker build --tag nornyx-academy:ci .
```

This re-proves both frozen installation surfaces and the production client build inside the image.

## Cross-platform notes

- Keep source, generated controls, and locks LF- and byte-stable. Do not normalize generated files
  differently on Windows.
- Always make subprocess text encoding explicit. Decorative Unicode in legacy output previously
  exposed a Windows console-code-page failure.
- Use `pathlib` and temporary directories in Python; never construct assumptions about `/tmp`,
  drive letters, or path separators into public results.
- Do not use pytest workers for the preserved lab suite. Cross-platform concurrency comes from CI
  jobs, not shared-checkout parallelism.
- Docker provides the production Linux boundary; Windows remains a required source/test platform.

## Explicit unavailability and troubleshooting

### Browser says the academy service needs attention

Confirm the API process is running and that `GET /api/v1/health` returns `200`. In two-process
development, confirm Vite is proxying to the same host and port as Uvicorn. The UI deliberately
keeps navigation available but will not fabricate catalog, scenario, evidence, or progress data.

### A framework lesson is unavailable

Re-run the frozen sync with `--extra crewai --extra langgraph`, then run conformance with both
`--require` flags. Do not catch the unavailable response and mark the lab complete. Verify CrewAI
telemetry controls are defined before any import.

### Live mode cannot start

The source environment needs the `live` extra, intentional network access, and a key entered in
the Settings page. The production Dockerfile deliberately installs only the deterministic and
adapter surfaces. A live request must return explicit unavailability when the provider client or
network is absent; it must never silently execute the deterministic planner under a live label.

### Contract validation reports a stale lock after a valid edit

That is expected: a semantic source change can be valid while the old generated controls and lock
are correctly stale. Review the source/effective/generated diffs, regenerate intentionally, and
never suppress `AN_LOCK_*` findings merely to make the screen green.

### Playwright cannot find Chromium

Run `npx playwright install chromium` from `frontend`. Linux CI uses `--with-deps`; a local Linux
host may need the same option. Keep the browser version from `package-lock.json` aligned with the
installed binary.

### Windows reports encoding or byte drift

Set `PYTHONIOENCODING=utf-8`, confirm Git has not rewritten generated LF files, and run the contract
drift gate before changing expected fixtures. Encoding repair must not weaken byte bindings.

### Frozen sync says the lock is stale

Run `uv lock --check` first. If `pyproject.toml` was intentionally changed, regenerate `uv.lock` in
a dedicated dependency/compatibility change and review the complete diff. Do not remove
`--frozen` from automated gates.

## Upgrade workflow

Nornyx and adapter upgrades are compatibility projects, not routine version bumps. Follow the
full procedure in [Nornyx compatibility and upgrade policy](NORNYX_COMPATIBILITY.md): audit exact
tags and commits, diff source semantics, update exact pins and the machine-readable compatibility
record, regenerate artifacts, execute every backend/frontend/browser/container gate, review
decision codes/evidence/counters manually, update scoped explanations, and obtain independent
maintainer review. An upgrade fails if a framework disappears, a test skips, an artifact drifts
without review, or assurance language strengthens without a stronger enforcement architecture.

# Independent deployment verification

CI proves the repository builds and behaves correctly **on controlled runners**.
That is a different claim from: a person on their own machine can obtain, build,
start and use this product by following the documentation.

This procedure tests the second claim. It exists because the machine this
project was developed on has an unusual characteristic — HTTPS interception by
local security software — and a product that only works there is not portable,
however green the pipeline is.

## What makes a run count

**Use a machine that has never built this project.** A disposable VM or a
freshly provisioned host. A machine with a warm Docker cache, an existing clone,
or dependencies already present cannot distinguish "this builds from nothing"
from "this builds here".

**Do not apply undocumented fixes.** Follow the repository documentation and the
command below, nothing else. If you find yourself editing a certificate store,
setting a proxy variable, or installing something the docs never mention, stop:
that is the finding. Write down what you had to do and report it, because the
next person will hit the same wall.

**The script will not repair your machine.** If Docker is missing, or a package
registry is unreachable, it records an environment failure and stops. A script
that installs its own prerequisites and then reports success has proved only
that it can install prerequisites.

## Prerequisites, in three kinds

Keeping these apart is the point. A verifier that quietly needs a host toolchain
would be the very portability dependency it exists to detect — and the operator
would install exactly what the documentation asked for, then be told afterwards
to install something else.

| Kind | What | Why |
|---|---|---|
| **Product** | Docker, Docker Compose v2 | What the [README](../README.md) asks an operator to install to run Nornyx Lab |
| **Verification harness** | bash, git, curl | What the script itself needs to execute. Checked up front, before the long build, and reported as *harness* prerequisites |
| **Not required on the host** | Python, Node, npm, `uv`, Nornyx | Anything needing a Python runtime executes inside the already-built production image |

If the script reports a missing harness prerequisite, that is a limitation of
the harness, not a finding about the product. It is still an environment
failure — the run cannot proceed — but it says which kind it is.

## Procedure

1. On the clean machine, install the product prerequisites: Docker with Compose
   v2. The harness also needs bash, git and curl, which most systems already
   provide; the script checks and names them before doing any work.

2. Clone the repository and check out the commit under test:

   ```bash
   git clone https://github.com/mazinmarji/nornyx-lab.git
   cd nornyx-lab
   git checkout <sha-under-test>
   ```

3. Run the verification:

   ```bash
   ./scripts/verify_independent_deployment.sh
   ```

   It takes roughly 5–15 minutes, most of it building the image with
   `--no-cache` so no local cache can hide a broken dependency path.

4. Read the verdict, and keep the `verification-evidence/` directory.

## What it checks

| Step | Condition |
|---|---|
| 1 | Records OS, architecture, Docker, Compose, git, repository SHA and whether the tree is dirty. Host Python and Node are noted as present-or-not for context only; neither is used |
| 2 | Product and harness prerequisites present, and port 8000 free — **reported, never installed** |
| 3 | `frontend/package-lock.json` is committed, so the documented build is reproducible |
| 4 | `docker build --no-cache --pull` succeeds, exercising `npm ci` against the lockfile and Python resolution with nothing cached |
| 5 | `docker compose up -d` starts the documented composition |
| 6 | Polls `/api/v1/health` until healthy rather than sleeping a fixed time |
| 7 | `GET /` serves the application shell, not only the API |
| 8 | The five-minute scenario runs **inside the production container** |
| 9 | Ungoverned records `1/1` and `executed`; governed records `0/0` and `prevented_before_execution` — parsed by the Python **inside the image**, not on the host |
| 10 | The learner record survives `docker compose restart`, which the named volume promises |
| 11 | Writes `verdict.json` and captures logs, image metadata and every command's output |

### On step 9

`0/0` on its own is not a prevention — an action nobody planned also records
`0/0`. The check therefore requires **both** paths: the ungoverned run showing
`1/1` from the same plan is what makes the governed `0/0` interpretable as
prevention. If the governed path reports `not_planned` instead of
`prevented_before_execution`, that is a failure even though the numbers look
identical.

## Reading the result

| Exit | Verdict | Meaning |
|---|---|---|
| `0` | `pass` | The documented path works on this machine |
| `1` | `product-failure` | The environment was adequate; something in the product did not do what the documentation says |
| `2` | `environment-failure` | This machine could not supply what the documented path needs. **Not a finding about the product** — but if the prerequisite is one the docs never mention, the documentation is the defect |
| `3` | usage | The script was invoked incorrectly |
| `4` | `verifier-failure` | The instrument could not complete its own check. **This run says nothing about the product**; rerun after the verifier is repaired |

### Why `verifier-failure` exists

The first independent run reached the real production scenario, and the semantic
checker then died on a shell quoting bug. The harness reported
`product-failure` — attributing a defect to Nornyx for a fault in its own
instrument. That is the wrong evidence semantics, and the distinction now has a
result of its own.

The boundary is deliberate. Malformed or contract-violating *product output* is
still a product failure, because producing a well-formed response is the
service's job. `verifier-failure` means only this: the instrument could not
decide.

A build that fails because a package registry is unreachable is reported as an
environment failure, with the matching text from the build log kept in evidence.
That distinction matters: an intercepting proxy and a broken Dockerfile produce
the same red output, and treating them the same would either excuse a real
defect or invent one.

## The acceptance gate

Only this combination accepts:

```
exit 0   verdict: "pass"   completed: true
```

on an eligible independent environment. Every other result — including
`verifier-failure` — leaves B5 acceptance pending.

## What this does not establish

- **It is not a governance claim.** It checks that the documented deployment
  path works and that the counters mean what the curriculum says. The assurance
  boundary is unchanged: the control remains cooperative and in-process, and
  [ASSURANCE.md](ASSURANCE.md) still bounds what any run here can support.
- **It is not a substitute for CI.** CI runs the full test suite across
  platforms. This runs one deployment on one machine.
- **One passing run proves one machine.** Portability is evidence accumulated
  across different operating systems, architectures and networks. Record which
  machine produced each result.

## Execution history

Recorded so a later reader knows what has and has not been attempted. No
`verification-evidence/` files are committed; these are summaries of runs
performed elsewhere.

### 2026-08-09 — first genuine independent execution

Commit `25b13e9`, on a fresh remote Ubuntu 24.04.4 LTS x86_64 host with Docker
Engine 29.1.3, Compose v2, no pre-existing images or containers, a fresh clone,
and no proxy or TLS environment variables.

The run reached the real production scenario. Steps 1–8 passed: the image built
from scratch in 82s, the composition started, health returned in 4s, the SPA was
served, and the five-minute demo executed inside the container. Step 10
persistence passed.

**Step 9 crashed** with `NameError: name 'attempts' is not defined`, and the
harness reported `product-failure` with exit 1.

That verdict was wrong in kind. The semantic checker was a Python program
embedded in a shell string whose quoting bash rewrote; the failure was in the
instrument, not in Nornyx. **It is not evidence of a governance or counter
defect.** The correction — moving the checker into a packaged module and adding
`verifier-failure` — is what this history entry exists to explain.

**B5 acceptance remains pending.** It requires a new disposable environment to
run the corrected verifier and produce exit 0 with `verdict: pass`.

## Reporting

Attach the `verification-evidence/` directory, or at minimum `verdict.json` and
`environment.txt`, so a reader knows which machine the result describes. A pass
with no environment record is not a portability claim about anything in
particular.

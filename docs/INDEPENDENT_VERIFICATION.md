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

## Procedure

1. On the clean machine, install only what the [README](../README.md) requires
   for the container path: Docker with Compose v2. Nothing else.

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
| 1 | Records OS, architecture, Docker, Python, Node, npm, git, repository SHA and whether the tree is dirty |
| 2 | Prerequisites present — **reported, never installed** |
| 3 | `frontend/package-lock.json` is committed, so the documented build is reproducible |
| 4 | `docker build --no-cache --pull` succeeds, exercising `npm ci` against the lockfile and Python resolution with nothing cached |
| 5 | `docker compose up -d` starts the documented composition |
| 6 | Polls `/api/v1/health` until healthy rather than sleeping a fixed time |
| 7 | `GET /` serves the application shell, not only the API |
| 8 | The five-minute scenario runs **inside the production container** |
| 9 | Ungoverned records `1/1` and `executed`; governed records `0/0` and `prevented_before_execution` |
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

A build that fails because a package registry is unreachable is reported as an
environment failure, with the matching text from the build log kept in evidence.
That distinction matters: an intercepting proxy and a broken Dockerfile produce
the same red output, and treating them the same would either excuse a real
defect or invent one.

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

## Reporting

Attach the `verification-evidence/` directory, or at minimum `verdict.json` and
`environment.txt`, so a reader knows which machine the result describes. A pass
with no environment record is not a portability claim about anything in
particular.

# Nornyx Feedback Gateway

A small hosted service that receives consented Nornyx Academy learner feedback
and records one GitHub issue per feedback session.

This is a **separate distribution on purpose**. It is the only component in the
architecture that holds GitHub write authority, and a learner installation must
contain none — so it is not a package inside `nornyx-lab`, it is not copied into
the learner image, and it has its own lock file, image, and CI job.

The full design, privacy boundary, and claims audit live in
[`../docs/LEARNER_FEEDBACK.md`](../docs/LEARNER_FEEDBACK.md). This file covers
only how to run it.

## Status

**Deployment-ready. Not deployed.** No instance has been provisioned, and no
production URL exists in this repository. Until an operator deploys one, learner
feedback is saved locally and never sent.

## What it does

1. receives a versioned `nornyx.academy.learner_feedback.v1` payload;
2. validates it as hostile external input — enums, ranges, length caps, unknown
   fields refused;
3. renders it into an issue body in which every caller-supplied string either
   has a syntax that carries no meaning in Markdown or sits inside a fence, and
   in which the session's write key is replaced by a one-way public marker;
4. recomputes the payload digest and refuses one that does not match;
5. creates or updates exactly one issue per feedback session, **per replica**;
6. returns a minimal status that does not name the intake repository.

### The session write key is never published

The intake is unauthenticated, so a session's UUID is what authorises
overwriting that session's issue. It is therefore never written to GitHub. The
issue carries `sha256(uuid)` instead — in the title, in the recovery comment, in
the summary, and in the embedded JSON — and the gateway's database is keyed on
that marker too. Derivation is deterministic, so recovery after database loss
still works; it is a plain digest rather than a keyed MAC precisely so it does
not depend on gateway-held state that a redeploy would lose.

### Scope of "one issue per session"

Synchronisation is serialised per feedback session **within one process**. That
makes the guarantee real for the single-replica deployment described here: two
simultaneous first writes for the same session cannot both create.

It is **not** distributed coordination. Two replicas sharing an intake
repository could still race on a session's first write and produce two issues.
Run one replica, or add genuinely shared coordination before scaling out — this
service does not provide it and does not claim to.

## What it must not do

Execute learner content, evaluate templates, run shell commands, modify source
files, generate code, open pull requests, invoke coding agents, or merge
anything. Feedback is data.

## Run it

```bash
uv sync --frozen --extra dev
uv run --frozen pytest -q
```

```bash
uv run --frozen uvicorn nornyx_feedback_gateway.app:create_app --factory --port 8080
```

```bash
docker build --tag nornyx-feedback-gateway:0.1.0 .
```

## Configure it

The token is a deployment secret. Inject it at runtime — never as a build
argument, which would record it in the image history.

```bash
docker run --rm -p 8080:8080 \
  -e NORNYX_FEEDBACK_GITHUB_REPOSITORY=owner/nornyx-feedback-intake \
  -e NORNYX_FEEDBACK_GITHUB_TOKEN="$TOKEN" \
  -e NORNYX_FEEDBACK_DESTINATION_VISIBILITY=private \
  -e NORNYX_FEEDBACK_DB=/var/lib/nornyx-feedback/gateway.db \
  -v nornyx-feedback:/var/lib/nornyx-feedback \
  nornyx-feedback-gateway:0.1.0
```

Use a fine-grained token or GitHub App scoped to issues on the intake repository
alone. With no repository and token configured the service still starts, reports
`github_configured: false` on `/health`, and refuses feedback with
`503 github_not_configured` rather than attempting an unauthenticated write.

Run **one replica** unless you have added shared coordination: the one-issue-per-
session guarantee is per process (see above).

Put TLS termination, WAF rules, network-level DDoS protection, and durable rate
limiting in front of it. The in-process limiter is a fixed window in memory: it
is bounded and does expire clients, but it does not survive a restart and does
not coordinate across replicas.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | liveness, whether a destination is configured, its visibility |
| `POST` | `/v1/feedback` | one feedback session; `202` with `created` / `updated` / `unchanged` |

There is no OpenAPI document and no docs page: nothing here should advertise
itself to a scanner.

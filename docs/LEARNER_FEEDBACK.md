# Learner feedback and validation

This is the canonical document for the feedback feature. Other files link here
rather than restating it.

## What this is for

Nornyx Academy can already say what a learner has *demonstrated*. It could not
say what a learner *experienced*. Feedback closes that gap for the maintainers,
and for nothing else.

> **Feedback is research instrumentation. It is not evidence of competence.**

The academy keeps four different kinds of thing apart, and this feature adds the
first one without touching the other three:

```
learner perception
    ≠ Academy assessment evidence
    ≠ learner-authored competence evidence
    ≠ external human-observation evidence
```

Feedback never influences assessment scoring, module completion, concepts
mastered, concepts pending evidence, concepts requiring re-demonstration,
capstone eligibility, competence revision, or `AdvancedStanding`. That is
enforced three ways in `tests/academy/test_feedback_isolation.py`: a behavioural
regression comparing identical work rated 1/5 against the same work rated 5/5,
an AST check that no competence module imports the feature, and a source check
that no competence module names a feedback table.

## Architecture

```
Learner browser
      │  ratings and comments only
      ▼
Local Nornyx Academy backend
      ├─ derives the authoritative Academy context
      ├─ writes the record to local SQLite
      │
      │  only after explicit consent
      ▼
Hosted Nornyx Feedback Gateway          ← the only holder of GitHub authority
      ▼
GitHub API
      ▼
Feedback intake repository
```

There is deliberately **no** path from a learner installation to GitHub. The
browser cannot reach an external host at all: the academy serves
`connect-src 'self'`, so the only network destination the page has is its own
backend.

| Component | Where | Holds a GitHub credential |
|---|---|---|
| React UI | `frontend/src` | no — and cannot reach any external host |
| Academy backend | `src/nornyx_lab/academy/feedback*.py` | no |
| Feedback gateway | `gateway/` — a separate distribution | yes, injected at runtime |

`gateway/` is a separate project with its own `pyproject.toml`, `uv.lock`,
`Dockerfile`, tests, and CI job. The learner `Dockerfile` copies an explicit
path list that does not include it, `.dockerignore` excludes it, and
`test_the_learner_image_does_not_contain_the_gateway` asserts both.

## What is collected

### Module feedback (optional, after a lesson)

Learner-supplied: clarity 1–5, confidence 1–5, difficulty
(`too_easy` / `right_level` / `too_hard`), self-assessment
(`understood` / `partly_understood` / `still_confused`), and an optional comment
of at most 2000 characters.

### Course feedback (optional)

Learner-supplied: overall clarity, progression, usefulness, and final confidence
(each 1–5), overall difficulty, recommendation (`yes` / `maybe` / `no`), and
optional most-helpful module, most-confusing module, missing topic, and comments.

### Server-derived context

Never accepted from the browser. Derived at the moment a rating is stored:

| Field | Source |
|---|---|
| feedback schema id, session id, record id, timestamps | this backend |
| module id | the route, validated against the catalog |
| module status, assessment score, pass/fail, attempt count | the learner record |
| competence semantic revision | `content/competence.json` |
| academy, Nornyx, adapter, API, content versions | installed package metadata |
| session elapsed seconds | server clock, session open → record written |
| learning path id | **always null** — see below |

`learning_path_id` stays null because every module belongs to at least two
authored paths and this installation records no chosen path. There is no
authoritative answer, so no answer is given. Unknown data stays unknown.

The request models carry perception fields only and forbid unknown fields, so a
modified client that posts `assessment_score` gets a 422 rather than having it
quietly dropped — proved by `test_a_browser_cannot_author_its_own_academy_context`.

### Never collected

Learner name, email address, GitHub identity, hostname, OS username, filesystem
paths, API keys, environment variables, hardware fingerprint, browser
fingerprint, stable device identifier, IP address, and raw assessment answers.
The application does not persist IP addresses anywhere.

## Session identity

Each validation session gets one `uuid4`, drawn from the operating system's
CSPRNG. It is derived from nothing about the learner, GitHub, the network, the
browser, the machine, or the hardware.

It is a **correlation identifier, not an authenticated identity**. It groups one
session's module and course feedback so a maintainer can read them together. A
modified or malicious client can present any identifier it likes, which is
exactly why the gateway treats everything it receives as untrusted input.

The browser never supplies the identifier: the backend uses its own open
session, so client-side forgery is not something to validate against — it is
not possible through the API.

## Privacy terminology

This feature is **not** described as anonymous, and the product does not use
that word for it. The honest formulations are:

> No identifying information is intentionally collected by Nornyx Lab.

> Pseudonymous learner feedback.

Three reasons the stronger claim would be false:

1. a learner can type identifying information into a free-text box, and the text
   is transmitted exactly as typed — sanitising it would corrupt the research
   material, so the product warns instead;
2. hosting and network infrastructure between the learner and the gateway
   processes network metadata that this application neither controls nor sees;
3. GitHub keeps its own logs and retention policies for anything stored there.

The boundary is: **the application itself does not persist IP addresses.** The
gateway holds a client address transiently, in memory, as a rate-limit bucket
key; it is never written to its database, never logged, and never returned.

## Consent

Nothing leaves the installation before an explicit opt-in. The checkbox is never
pre-checked, and absence of a decision is not a decision —
`POST /api/v1/feedback/consent` with an empty body is a 422.

```
not_asked ──grant──▶ granted ──revoke──▶ revoked ──grant──▶ granted
    │                   │                    │
    └─ no transmission ─┘                    └─ no future transmission
```

`granted` is the only state in which the service will construct a transport
call, and the state is read from SQLite rather than from the request. Consent
events are stored append-only with their timestamp and the version of the
consent wording that was shown, because a grant only means something alongside
what it was a grant *of*.

After consent, later feedback in the same session syncs automatically. That is
disclosed in the consent copy before the checkbox.

**Revocation stops future synchronisation. It does not remove anything already
received, and the product never says otherwise.**

## Local persistence

Five additive tables in the existing academy SQLite database:
`feedback_sessions`, `feedback_consent_events`, `module_feedback`,
`course_feedback`, `feedback_sync_state`. All are created with
`CREATE TABLE IF NOT EXISTS`. Nothing in `feedback.py` issues `ALTER`, `UPDATE`,
or `DELETE` against `module_progress`, `assessment_attempts`, or
`capstone_runs`.

The local write happens before any network call is considered and is never
rolled back by a delivery failure. A learner with no internet loses nothing.

One row per `(session, module)` and one course row per session: resubmitting
revises rather than duplicating, so a learner changing their mind is recorded as
a correction.

## Deletion and reset

These are separate controls, deliberately, in both directions:

* `POST /api/v1/progress/reset` clears learner progress and **keeps** feedback.
  The reset dialog says so and links to where feedback can be deleted.
* `DELETE /api/v1/feedback` removes local feedback and **keeps** progress.

Deleting locally is not a remote deletion. Where something had already been
sent, the response says exactly that and does not imply a recall.

## Synchronisation and idempotency

One issue per feedback session. Never one per module.

```
Session
 ├─ module feedback F0
 ├─ module feedback F1
 ├─ module feedback F2
 └─ course feedback
```

Every sync sends the whole session, so the same session always renders to the
same issue body and a retry is indistinguishable from a first attempt.

`payload_digest = sha256(canonical JSON of the payload minus its sync envelope)`.
The academy skips the call entirely when the digest matches the last confirmed
delivery. At the gateway:

| Situation | Action |
|---|---|
| known session, same digest | no-op — not even an edit |
| known session, new digest | update the same issue |
| unknown session, marker found on GitHub | update, and re-learn the number |
| unknown session, nothing found | create |

The third row is the one that matters. A create can succeed on GitHub and still
fail to reach the gateway — a timeout after the write, a restart in between.
Recovery lists labelled issues, matches the deterministic title, and confirms
identity with the full session UUID in a body marker. The issues listing is used
rather than the search API because search indexing lags, and a lagging index is
precisely how a retry produces a duplicate.

Covered by executable tests: timeout, ambiguous timeout after remote create,
retry, process restart, gateway database loss, 401, 403, 404, 422, 5xx,
malformed response, and repeated identical sync.

There is **no retry loop inside a learner HTTP request**. One attempt, one
honest answer, and an explicit "try again" control.

## Outage behaviour

A gateway or GitHub outage cannot block learning and cannot lose feedback. The
record is already committed; the delivery state records `failed` with a coarse
error code. Even an unexpected exception from the transport comes back as a
saved rating rather than a failed request.

The learner sees, verbatim from the backend:

| State | Message |
|---|---|
| saved, no consent | Feedback saved on this computer. Nothing has been sent to the maintainers. |
| consent given | Feedback saved on this computer. Future feedback from this learning session will also be sent to the maintainers. |
| delivery failing | Your feedback is saved locally. Sending it to the maintainers is temporarily unavailable. |
| no endpoint configured | Feedback is saved locally. This installation is not configured to send feedback to the maintainers. |

No GitHub token, stack trace, raw HTTP response, gateway URL, or filesystem path
is ever shown. The browser renders `learner_message` from the response and never
composes its own success text, so the UI cannot say "sent" while the record says
otherwise.

## Untrusted learner text

Every field arriving at the gateway is hostile input. Comments are stored and
transmitted **exactly as typed** — sanitising them would destroy their research
value — and are made inert at the point of rendering instead.

The whole argument is one sentence: **no learner-authored character is ever
emitted as Markdown.** Learner text appears only inside a fenced code block
whose fence is computed to be one backtick longer than the longest backtick run
in the text, so the text cannot close its own fence. GitHub does not parse
mentions, issue references, or Markdown inside a fenced block.

Everything outside a fence is generated from values Pydantic has already
constrained to enums, bounded integers, or a strict identifier pattern. The
issue title is derived from the session UUID alone; labels, repository, and
issue state come from deployment configuration. There is no field a learner can
write that reaches a position where it could be interpreted.

Tested against `@maintainer`, `@codex`, `#123`, HTML and `<script>` tags, triple
and quadruple backticks, shell commands, `${{ secrets.GITHUB_TOKEN }}`,
Actions-looking YAML, JSON-looking text, prompt injection, long Unicode and
emoji input, and control-character edge cases — each preserved verbatim and each
proved to sit inside a fence. The check that proves it has its own negative
control, because an oracle that always returns true would prove nothing.

The gateway does not execute learner content, evaluate templates, run commands,
modify files, generate code, open pull requests, invoke agents, or merge
anything. It reads a payload and writes one issue body.

## GitHub credential boundary

Only the hosted gateway holds GitHub write authority, through
`NORNYX_FEEDBACK_GITHUB_TOKEN` and `NORNYX_FEEDBACK_GITHUB_REPOSITORY`.

* deployment secret only, injected at runtime;
* never committed, never persisted, never returned, never logged;
* excluded from the config object's `repr`;
* not a build argument, so it cannot reach an image layer;
* prefer a fine-grained token or GitHub App scoped to issues on the intake
  repository alone.

CI verifies this rather than asserting it: the GitHub boundary is substituted in
every gateway test, `test_no_ci_job_requires_a_real_github_credential` fails if
any job references a repository secret, and the container job inspects
`docker history` and the image's default environment.

An unconfigured gateway **fails closed**: it returns `503 github_not_configured`
rather than attempting an unauthenticated write.

## Intake repository

Architecturally the destination should be a **private raw feedback intake
repository**, not the public engineering issue tracker:

```
learner feedback → private intake → human aggregation → evidence-backed issue → nornyx-lab
```

The repository is configurable and no default is assumed to exist. If the
configured destination is public, the consent copy must say that learner text
may become publicly visible — `NORNYX_FEEDBACK_DESTINATION_VISIBILITY=public`
makes the UI say exactly that. The default is `unknown`, and the copy then says
the installation cannot confirm whether the destination is public or private
rather than implying privacy it cannot verify.

## Configuration

Learner installation (all optional, none secret):

| Variable | Default | Meaning |
|---|---|---|
| `NORNYX_FEEDBACK_ENDPOINT` | unset | gateway URL; unset means local-only |
| `NORNYX_FEEDBACK_DESTINATION_VISIBILITY` | `unknown` | `public` / `private` / `unknown` |
| `NORNYX_FEEDBACK_TIMEOUT_SECONDS` | `10` | clamped to 1–60 |

The endpoint must be `https://`, except on loopback where `http://` is accepted
for local testing. Redirects are refused rather than followed: a redirect is a
request to send the learner's words somewhere other than the configured
destination.

Gateway deployment:

| Variable | Default | Meaning |
|---|---|---|
| `NORNYX_FEEDBACK_GITHUB_REPOSITORY` | unset | `owner/name` |
| `NORNYX_FEEDBACK_GITHUB_TOKEN` | unset | **secret**, runtime injection only |
| `NORNYX_FEEDBACK_GITHUB_API` | `https://api.github.com` | |
| `NORNYX_FEEDBACK_GITHUB_TIMEOUT_SECONDS` | `10` | outbound bound |
| `NORNYX_FEEDBACK_DB` | `gateway.db` | sync-state store |
| `NORNYX_FEEDBACK_DESTINATION_VISIBILITY` | `unknown` | reported on `/health` |
| `NORNYX_FEEDBACK_ISSUE_LABELS` | `learner-feedback` | comma-separated |
| `NORNYX_FEEDBACK_MAX_BODY_BYTES` | `65536` | request cap |
| `NORNYX_FEEDBACK_RATE_LIMIT_PER_MINUTE` | `30` | per client address |

## Abuse controls

A public endpoint is untrusted internet input. Proportionate, in the service:
strict schema validation with unknown fields forbidden, a streamed body-size cap
enforced before parsing, bounded text fields, numeric ranges, enums,
deterministic UUID validation, an explicit outbound timeout, idempotency, and
logs that carry a truncated session id and an outcome and nothing else.

Explicitly **not** here, and belonging at the reverse proxy or cloud edge: TLS
termination, WAF rules, network-level DDoS protection, IP reputation, and
durable rate limiting across replicas. The in-process limiter is a fixed window
in memory; it does not survive a restart and does not coordinate between
instances. No user accounts and no authentication system are built.

## Reading the results

Per module: sample count, average clarity, average confidence, difficulty
distribution, understanding distribution, assessment pass rate among
feedback-bearing records, and a confidence/pass mismatch count. Per course:
sample count, clarity, progression, usefulness, and recommendation
distribution. The sample count is always reported.

Interpretation is bounded, and the API says so in its own response:

| Observation | What it is | What it is not |
|---|---|---|
| high confidence + failed assessment | an investigation signal | proven false confidence |
| low clarity score | learner-reported low clarity | proven defective teaching |

None of it supports a causal conclusion, and none of it is a measurement of
educational effectiveness. `GET /api/v1/feedback/summary` covers **one
installation** and is maintainer instrumentation; it is not shown in the learner
UI.

## Deployment status

**The gateway is implemented and deployment-ready. Public feedback
synchronisation is not yet operational.**

No gateway has been provisioned as part of this change, no production URL exists
anywhere in this repository, and the default learner deployment
(`docker compose up --build`) has no feedback endpoint and no GitHub credential.
Local feedback works fully; external sending is unavailable until an operator
deploys a gateway and configures `NORNYX_FEEDBACK_ENDPOINT`.

## Claims audit

Every significant claim this feature makes, classified against its evidence.

| Claim | Status | Evidence |
|---|---|---|
| Feedback has no effect on competence, mastery, completion, or standing | implemented and tested | `test_feedback_isolation.py` — behavioural, AST, and source checks |
| Feedback saves locally before any network call | implemented and tested | `test_feedback.py`, `test_feedback_sync.py` |
| Learning works with no internet | implemented and tested | `test_learning_works_with_no_network_configured_at_all` |
| Nothing is transmitted before explicit consent | implemented and tested | `test_nothing_is_transmitted_before_explicit_consent` (zero transport calls) |
| A learner installation holds no GitHub credential | implemented and tested | credential-symbol scan over shipped files; Dockerfile and `.dockerignore` checks |
| The backend derives authoritative context the browser cannot author | implemented and tested | `test_a_browser_cannot_author_its_own_academy_context` (13 forged fields) |
| The gateway creates one issue per session and updates it thereafter | implemented and tested | gateway idempotency suite against a substituted GitHub boundary |
| Retry and restart do not duplicate | implemented and tested | ambiguous-timeout and lost-database recovery tests |
| Learner free text stays inert | implemented and tested | 20-case hostile corpus, fence oracle with a negative control |
| A pre-H1 database migrates without altering evidence | implemented and tested | `test_feedback_migration.py` against literal pre-H1 DDL |
| The application does not persist IP addresses | implemented and tested | no column exists; gateway store holds only session→issue |
| The gateway is deployed and receiving feedback | **not implemented** | no gateway has been provisioned; stated as such above |
| Feedback is anonymous | **not claimed** | free text, network metadata, and GitHub retention all preclude it |
| Feedback measures educational effectiveness | **not claimed** | the summary response carries its own interpretation limit |
| Deleting local feedback removes it from GitHub | **not claimed** | the deletion response states the opposite |
| The destination is private | configuration-dependent | operator-set; default `unknown`, and the copy says so |

## Residual limitations

* A modified client can present any session identifier and any perception
  values. The gateway is designed on that assumption; the corpus is
  self-reported and should be read that way.
* Because the intake is unauthenticated by design — no accounts, no learner
  identity — anyone who learns a session identifier can post a payload carrying
  it and overwrite that session's issue. Session identifiers are `uuid4`, are
  never displayed to anyone but the learner whose session it is, and are not
  returned by the gateway, so this requires the identifier to leak first. The
  mitigation is that the intake is a **raw research feed**, not a system of
  record: a maintainer aggregates from it into an evidence-backed engineering
  issue, and should treat any single session as unverified. Adding
  authentication would mean building learner accounts, which this feature
  deliberately does not do.
* Assessment context in a payload is generated by the learner's own
  installation. It is Academy-generated evidence, not independent ground truth.
* GitHub mention-suppression relies on GitHub not parsing Markdown inside code
  fences. That is how it behaves and how the body is constructed; it is not a
  guarantee this repository can enforce on GitHub's renderer.
* The in-process rate limiter does not survive a restart or coordinate across
  replicas.
* Recovery scans a bounded number of pages of labelled issues. An intake
  repository with a very large number of labelled issues should be rotated.

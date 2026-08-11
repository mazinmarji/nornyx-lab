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
| module status | the learner record |
| assessment score, pass/fail, attempt count | admissible assessment attempts only |
| current competence revision | `content/competence.json` |
| revision the reported evidence was earned under | the governing admissible attempt |
| academy, Nornyx, adapter, API, content versions | installed package metadata |
| session elapsed seconds | server clock, session open → record written |
| learning path id | **always null** — see below |

`learning_path_id` stays null because every module belongs to at least two
authored paths and this installation records no chosen path. There is no
authoritative answer, so no answer is given. Unknown data stays unknown.

**Assessment context obeys evidence expiry.** The score, pass/fail, and attempt
count summarise only attempts the current competence contract still admits --
derived the same way concept mastery is, not read from the `module_progress`
aggregate. That aggregate accumulates across every attempt ever made with no
memory of the semantics each was earned under, so reading it would publish a
pass earned under a superseded revision as an assessment result under today's
meaning of that assessment. When nothing is admissible the fields are `null`,
which means *no current evidence* and is a different claim from `false`.

Two revisions are reported because they are two different facts:
`competence_revision` is what an assessment means today, and
`assessment_evidence_revision` is what the reported evidence was actually earned
under. They differ only when a prior revision was explicitly declared
compatible. Historical rows are never rewritten -- expiry is about admissibility,
not deletion.

`module_status` deliberately does **not** expire. Completion is activity
evidence; only the competence claim expires. A record showing `complete` with no
admissible assessment evidence is stating the truth: the learner did the work,
under rules that have since changed.

**Course feedback carries a different context.** It has no module status, module
score, or module pass/fail -- not even a placeholder -- because a course-level
rating has no module for those to be facts about, and a placeholder in a
research record is indistinguishable from an observation. It carries the
curriculum-wide admissible attempt total, the competence revision, the learning
path (null), and the session elapsed time.

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

### The write key is never published

Because the intake is unauthenticated by design, presenting a session's UUID is
what lets a caller overwrite that session's issue. So the UUID must not appear
in the issue — and it used to, three times over: in the summary line, in the
HTML recovery marker, and in the embedded JSON. Against a public intake
repository that published the exact locator needed to overwrite the record.

Two identifiers are now kept apart:

| | Value | Who sees it |
|---|---|---|
| **Write key** | the session `uuid4` | the learner's installation and the gateway, only |
| **Public marker** | `sha256(uuid)` | everything written to GitHub |

Only the marker reaches GitHub: the issue title carries its first twelve hex
characters, the recovery comment carries it in full, the summary line reports it
as *Session marker*, and the embedded JSON carries `session.session_marker` in
place of `session.session_id`. The gateway's own database is keyed on the marker
too, so no component downstream of the Academy stores a value that authorises a
write.

Recovery still works because derivation is deterministic — an incoming UUID
always produces the same marker, so a gateway that has lost its database can
still find the issue that already represents the session. That is also why the
derivation is a plain SHA-256 rather than an HMAC under a gateway-held key: a
secret that must be backed up to keep recovery working is a secret that will
eventually be lost. A `uuid4` has 122 bits of entropy, so the marker is not
reversible by search, and publishing it does not let a reader reconstruct the
key.

Because of that substitution the JSON embedded in the issue is **not** a
verbatim copy of the payload received, and is not described as one. Exactly one
field is transformed; every rating, comment, and context value is what the
installation sent. The digest is unaffected — it is computed over the payload as
received, so both sides still agree on content identity.

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

One issue per feedback session, never one per module — a **single-replica**
guarantee, for the reasons set out under *Concurrency* below.

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
delivery.

**The gateway does not trust the digest it receives.** `sync.payload_digest` is
a field in an unauthenticated request, and content identity decides whether a
payload is a no-op, an update, or a create -- so accepting the sender's value
would let a stale digest suppress a real update, or let one payload claim
another's identity. After validation the gateway canonicalises the parsed
payload with the same three rules the Academy uses (drop `sync`, sort keys, no
insignificant whitespace), recomputes SHA-256, and refuses a mismatch with
`422 digest_mismatch` before touching GitHub or the synchronisation store. Every
downstream decision uses the recomputed value. A committed real-Academy payload
in the gateway suite keeps the two canonicalisations provably in step.

At the gateway:

| Situation | Action |
|---|---|
| known session, same digest | no-op — not even an edit |
| known session, new digest | update the same issue |
| unknown session, marker found on GitHub | update, and re-learn the number |
| unknown session, nothing found | create |

The third row is the one that matters. A create can succeed on GitHub and still
fail to reach the gateway — a timeout after the write, a restart in between.
Recovery runs entirely on the derived marker:

```
incoming private session UUID
  → gateway derives sha256(uuid), the public marker
  → lists labelled issues and matches the deterministic title,
    whose fragment is a prefix of that marker
  → confirms identity against the full marker in the body comment
  → updates the issue it found
```

The raw UUID is never written to GitHub, so recovery never looks for one. The
issues listing is used rather than the search API because search indexing lags,
and a lagging index is precisely how a retry produces a duplicate.

**Concurrency, and the exact scope of the guarantee.** Lookup, recovery, create,
and remember are not one atomic step, so two simultaneous requests for the same
previously unseen session could both decide to create. Synchronisation is
therefore serialised per feedback session, and
`gateway/tests/test_concurrency.py` first *demonstrates* the duplicate against
the unserialised sequence before requiring the application to prevent it.

That guarantee is **within one gateway process**. One issue per session holds
for the single-replica deployment this gateway documents. It is not distributed
coordination: two replicas sharing an intake repository could still race on a
session's first write, and nothing here claims otherwise. Exactly-once creation
across replicas would need genuinely shared coordination, which is not
implemented.

Covered by executable tests: timeout, ambiguous timeout after remote create,
retry, process restart, gateway database loss, 401, 403, 404, 422, 5xx,
malformed response, repeated identical sync, forged digest, stale digest, and
two simultaneous first writes.

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

The claim, stated precisely: **every caller-supplied string either has a syntax
that carries no meaning in Markdown, or is emitted only inside a fenced block.**
No caller-supplied character reaches a position where Markdown would interpret
it.

The two halves:

* **Free text is fenced.** Comments appear only inside a fenced code block whose
  fence is computed to be one backtick longer than the longest backtick run in
  the text, so the text cannot close its own fence. GitHub does not parse
  mentions, issue references, or Markdown inside a fenced block.
* **Everything else has a syntax.** Timestamps must match an explicit ASCII
  form — `YYYY-MM-DDTHH:MM:SS[.ffffff](Z|±HH:MM)` — *and then* parse to a real
  timezone-aware instant. Both halves are needed, and parsing alone is not
  enough: `datetime.fromisoformat` accepts any single character as the
  date/time separator, so ``2026-08-11`12:00:00+00:00`` is a valid instant that
  would have closed its own code span in the rendered summary, and the newline
  variant would have escaped the line entirely. Versions and competence
  revisions match a character set that excludes backticks, newlines, brackets,
  pipes, and the at sign. Identifiers, ratings, enums, counts, and the digest
  were already constrained. A value outside its syntax is a malformed payload
  and is refused, not escaped.

This covers the *whole* wire surface, not only the comment fields. An earlier
version of this feature bounded timestamps and versions by length alone, which
left a caller able to put a backtick, a newline, a mention, or a Markdown link
into the summary a maintainer reads.
`gateway/tests/test_wire_surface_inertness.py` enumerates every string-valued
position in a real payload and attacks each with the same hostile corpus, so a
field added later is attacked automatically rather than being quietly exempt.

The issue title is derived from a prefix of the public correlation marker;
recovery verifies the full marker in the body. Labels, repository, and issue
state come from deployment configuration.

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
deterministic UUID validation of the incoming write key, an explicit outbound
timeout, idempotency, and logs that carry a prefix of the derived public marker
and an outcome — never the session identifier itself.

The limiter forgets clients. Buckets are swept globally on a schedule rather
than only when the same address returns, so an address seen once and never again
disappears; the bucket count is hard-bounded with deterministic
least-recently-active eviction; and access is mutex-guarded because Uvicorn
dispatches the endpoint on worker threads. That is what makes "client addresses
are held transiently" a property of the code rather than an intention.

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
| The gateway creates one issue per session and updates it thereafter, **within a single replica** | implemented and tested | gateway idempotency suite plus a barrier-based concurrency test that first demonstrates the duplicate |
| Retry and restart do not duplicate | implemented and tested | ambiguous-timeout and lost-database recovery tests |
| Two simultaneous first writes do not duplicate | implemented and tested, single replica only | `test_concurrency.py`; the unserialised sequence is shown to duplicate first |
| Exactly-once creation across multiple gateway replicas | **not implemented** | no shared coordination exists; stated as a limitation |
| The gateway verifies the payload digest itself | implemented and tested | forged, stale, and per-field mutation attacks; a real-Academy golden payload |
| Feedback assessment context obeys evidence expiry | implemented and tested | `test_feedback_evidence_expiry.py`, including the pass-under-A-report-under-B attack |
| Every caller-supplied string is inert, not only free text | implemented and tested | full wire-surface sweep over every string position, plus the 20-case free-text corpus; both oracles have negative controls |
| A pre-H1 database migrates without altering evidence | implemented and tested | `test_feedback_migration.py` against literal pre-H1 DDL |
| The application does not persist IP addresses | implemented and tested | no column exists; gateway store holds only session→issue |
| Client addresses are held only transiently | implemented and tested | global sweep, bounded buckets, deterministic eviction, 5,000-key retention test |
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
  identity — anyone holding a session's `uuid4` can post a payload carrying it
  and overwrite that session's issue. What the published record no longer does
  is hand them that value: GitHub receives only the one-way marker, the gateway
  stores only the marker, and the gateway never returns either. The UUID exists
  in the learner's own installation and in transit to the gateway, so the
  residual exposure is a compromised installation or a broken TLS path, not a
  reader of the intake repository. The wider mitigation is unchanged: the intake
  is a **raw research feed**, not a system of record, and a maintainer should
  treat any single session as unverified. Adding authentication would mean
  building learner accounts, which this feature deliberately does not do.
* Assessment context in a payload is generated by the learner's own
  installation. It is Academy-generated evidence, not independent ground truth.
* GitHub mention-suppression relies on GitHub not parsing Markdown inside code
  fences. That is how it behaves and how the body is constructed; it is not a
  guarantee this repository can enforce on GitHub's renderer.
* The in-process rate limiter does not survive a restart or coordinate across
  replicas. It is bounded and does forget clients, but it is a per-process
  control, not a distributed one.
* **One issue per session is a single-replica guarantee.** Synchronisation is
  serialised per session within one gateway process. Two replicas sharing an
  intake repository could still both create on a session's first write. Closing
  that would need shared coordination, which is not implemented and is not
  claimed.
* Recovery scans a bounded number of pages of labelled issues. An intake
  repository with a very large number of labelled issues should be rotated.

# Contributing to Nornyx Academy

Nornyx Academy is both a product and an assurance teaching artifact. A contribution is complete
only when its learner interaction, executable behavior, assessment, schema, tests, and claims
agree. A polished page over a disconnected fixture is not acceptable.

Read these first:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
  [`docs/adr/0001-gui-first-academy-architecture.md`](docs/adr/0001-gui-first-academy-architecture.md);
- [`docs/ASSURANCE.md`](docs/ASSURANCE.md) and [`docs/SECURITY.md`](docs/SECURITY.md);
- [`docs/NORNYX_COMPATIBILITY.md`](docs/NORNYX_COMPATIBILITY.md);
- [`docs/MIGRATION_MAP.md`](docs/MIGRATION_MAP.md) and
  [`docs/CURRICULUM_COVERAGE.md`](docs/CURRICULUM_COVERAGE.md);
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the frozen environment and gate commands.

## Contribution workflow

1. Branch from current `main` and keep changes focused enough to review as one coherent claim.
2. Establish the current behavior with the narrowest relevant tests before editing.
3. Update the authoritative content/domain source before derived prose or presentation.
4. Run fast tests while iterating, then every definition-of-done gate affected by the change.
5. Review the final diff for secrets, learner data, caches, screenshots containing local paths,
   generated-environment files, and accidental notebook outputs.
6. Explain in the pull request what was preserved, changed, executed, tested, and deliberately left
   outside the claim.

Do not commit `.venv*`, `.uv-cache`, `node_modules`, `frontend/dist`, Playwright traces, local
SQLite progress, API keys, provider output, or host-specific paths.

## Separation of concerns

Keep these layers independent:

| Layer | Authoritative location | Must not become |
|---|---|---|
| Curriculum and paths | `src/nornyx_lab/academy/content/*.json` plus `labs/*/lab.toml` | JSX-only prose or an unversioned page list |
| Scenario domain | `academy/scenarios.py`, `foundations.py`, dedicated replacements, `capstone.py`, and preserved domain modules | UI animation, terminal transcript, or a test-only mock |
| Nornyx integration | direct released Python APIs and pinned adapters | invented semantics or scraped CLI prose |
| Public contract | `academy/schemas.py` and `/api/v1` | an untyped results dictionary |
| Assessment | `assessments.json` and `academy/assessments.py` | repository pytest, trivia, or click-through credit |
| Persistence | learner-record protocol and SQLite implementation | curriculum business logic or secret storage |
| Presentation | `frontend/src` | a second source of policy truth or fabricated fallback data |

The legacy CLI and notebooks may remain developer/compatibility utilities. No learner-facing
instruction may require them.

## Content definition of done

A new or changed module must:

- have a stable id, title, summary, why-it-matters statement, difficulty, estimated minutes,
  prerequisites, concept list, observable outcomes, interaction name, scenario id, and assessment
  id in the canonical authored data;
- appear in every intended path in `paths.json`, with path prerequisites, outcomes, effort, and
  completion criteria still accurate;
- preserve valid original concepts/assets when replacing a legacy lab and update the migration map
  with the exact classification and reason;
- add beginner explanation without weakening professional detail or changing released Nornyx
  semantics;
- tell the learner what input changed, what executed, what was observed, and what remains unknown;
- link prose claims to an executable interaction and meaningful assessment;
- update the human curriculum coverage matrix while keeping JSON as the machine-readable source;
- contain no setup instructions in the learner path.

There must be exactly one accounted disposition for every legacy id `00`–`24`. A new title or
catalog scenario id is not a migration unless a routed executor and behavioral tests implement it.

## Scenario definition of done

Every scenario must:

- be callable through a versioned service route and return `ScenarioRun` or `StructuredLabRun`;
- reject unknown or malformed inputs instead of coercing them into a plausible run;
- be deterministic by default at the serialized API boundary;
- use real released Nornyx APIs for any claimed parse, check, composition, generation, lock,
  authorization, approval, evidence, or adapter behavior;
- keep planner input/proposals, typed decisions, enforcement, business attempts/completions,
  evidence events/findings, and assurance claims structurally separate;
- return explicit `unavailable` when a required dependency or runtime surface is absent; never
  convert absence, exception, or empty evidence into success;
- use inert business callables and perform no email, payment, publication, repository push,
  package execution, MCP activation, upload, or other external business effect;
- isolate every legacy filesystem mutation in a per-run temporary copy and prove that committed
  fixtures are unchanged;
- redact host paths and secrets from returned data;
- state the safety boundary, exact enforcement surface, evidence producer, uncovered paths, and
  completion-eligibility rule;
- restore controlled experiments or return an explicit restoration failure.

If a module promises retry, loop, parallel, interrupt, resume, delegation, handoff, or multi-agent
behavior, its scenario must execute and identify that behavior. Descriptive cards or reconstructed
test data do not satisfy the promise.

## Assessment definition of done

Each module needs one public assessment definition whose answer is excluded from the GET response.
The assessment must:

- test transfer or interpretation through scenario prediction, ordering, bypass identification,
  policy/contract repair, evidence interpretation, or assurance correction;
- avoid pure vocabulary recall when an executable decision or claim can be tested;
- use stable option ids and an explanation that teaches why the selected reasoning is right or
  wrong;
- declare the module id, kind, minimum score, and concept mastery/review signals;
- treat order as significant only for ordering exercises and score unordered choices as a set;
- permit retries and persist every attempt without leaking the correct answer before submission;
- require a higher threshold and executable verification rows for the capstone;
- never award completion for visiting, expanding, or clicking through a page.

Add scoring tests for correct, incorrect, reordered, partial, duplicate, and unknown answers as
applicable. Verify that progress reaches `complete` only after both execution and assessment pass.

Changing which concepts an item tests, what counts as a correct answer, or the passing threshold
changes what existing learner evidence means. Bump the affected family revision in
`src/nornyx_lab/academy/content/competence.json` in the same change, and list the prior revision in
`compatible_with` only if evidence earned under it genuinely still holds. The digest gate in
`tests/academy/test_competence_contract.py` fails when a semantic edit arrives without that
decision; see [`docs/ACADEMY_DESIGN_PRINCIPLES.md`](docs/ACADEMY_DESIGN_PRINCIPLES.md).

## API and schema definition of done

The browser consumes structures, not prose conventions. For any public change:

- extend the Pydantic models first, keep `extra="forbid"`, and make unknown/indeterminate states
  explicit rather than overloading null, zero, or pass;
- keep `/api/v1` backward compatible or make a deliberate API-version change with migration notes;
- update matching TypeScript types and the API client in the same change;
- do not expose assessment answers, live-model secrets, local absolute paths, raw exceptions, or
  mutable internal objects;
- preserve security headers and `no-store` behavior on API responses;
- return 404 for unknown resources, 422 for invalid closed inputs, and 503 or a typed unavailable
  result for unavailable execution—never a fabricated 200 result;
- add API contract tests and component tests for loading, success, warning, failure, and unknown.

Diagnostics may report only fields returned by the released Nornyx API. In the pinned runtime that
means level, code, message, and semantic path; do not invent line or column locations.

## Frontend definition of done

Every primary operation must be usable with keyboard and pointer, responsive at desktop/tablet,
and readable on mobile. A frontend change must:

- preserve the skip link, visible focus, semantic headings/labels, keyboard navigation, and
  text/shape status cues;
- render loading, success, warning, failure, unavailable, and indeterminate as distinct states;
- never render a successful fallback when an API call fails or a field is missing;
- keep real `.nyx` authoritative in visual/source/control/diagnostic views;
- explain attempt/completion and evidence limitations near the observation;
- add component tests for material conditional states;
- extend the Playwright journey when the primary learner path changes;
- run axe on any new primary page or state and produce test-generated visual evidence where it is
  useful for review.

Use diagrams only when they explain an active relationship or execution state. Decorative graphs
do not count as an interaction.

## Honest-claim checklist

Any feature reporting learner standing (mastery, readiness, advanced completion, or similar) is
additionally reviewed against the acceptance contract in
[`docs/ACADEMY_DESIGN_PRINCIPLES.md`](docs/ACADEMY_DESIGN_PRINCIPLES.md).

Before adding or changing a material claim, answer:

1. What exact planner, graph node, tool, resource, artifact, workflow, or path is the target?
2. Which callable, adapter hook, gate, or external boundary was actually observed or enforced?
3. Was the result a declaration, check, composition, generated control, lock, decision,
   enforcement observation, counter, or evidence validation?
4. Which component produced each event and counter?
5. Which version, contract revision, artifact digest, approval, occurrence, and attempt are bound?
6. Which direct, async, distributed, delegated, unsupported, or unobserved path remains?
7. What adversary is in scope, and what result would falsify the claim?

Apply these fixed distinctions:

- Nornyx declares, checks, composes, generates, locks, decides, and validates supplied evidence.
  It is not a model, planner, orchestrator, framework, workflow engine, tool runtime, transport,
  identity provider, approver authenticator, unavoidable PEP, or independent attestor.
- A declaration is not an evaluated control; a decision is not enforcement; a generated control
  is not proof of runtime use.
- `0/0`, `1/0`, `1/1`, and unknown are different. Refusal text cannot settle a side-effect claim.
- Evidence integrity/conformance is not event truth, authenticity, completeness, or whole-system
  coverage unless a separate mechanism establishes each property.
- Approval validation does not authenticate the approver, mutate the Authorizer, or create a
  permanent capability. The demonstrated combined path is a gated crossing carrying an assertion.
- CrewAI coverage is the pinned synchronous `BaseTool._run` surface reached through native
  kickoff. LangGraph coverage is the pinned synchronous declared `StateGraph` node surface with
  occurrence metadata. Other paths remain unsupported or unwrapped unless separately executed.
- Cooperative in-process demonstrations support Tier 2 at most on the named surface. Do not write
  “the agent is governed,” “CrewAI is governed,” “the application is governed,” or any Tier 3
  claim without an independently enforced unavoidable architecture and independent observation.
- The academy demonstrates governance of inert targets. It is not itself governed by Nornyx merely
  because it uses Nornyx.

## Test definition of done

At minimum, a contribution must add the narrow tests that would fail if its educational claim
became false. Depending on scope, include:

- domain unit tests and deterministic serialized snapshots/assertions;
- positive, denial, malformed-input, unavailable, failure-injection, and bypass cases;
- API response/status/security-header tests;
- persistence and execution-plus-assessment completion tests;
- `.nyx` semantic equivalence, generated-control, diagnostic, and source-fixture immutability tests;
- adapter supported/unsupported inventory and no-silent-skip conformance tests;
- React component tests for structured rendering and error/unknown behavior;
- fresh-learner Playwright and axe coverage for a primary journey;
- Linux and Windows coverage for path/encoding/isolation changes;
- Docker build verification for dependency, static-build, or runtime changes.

Run the gates in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md). The full legacy suite is serial. CI
must install both framework extras, parse pytest JUnit results, and fail if any required test was
skipped. Never solve a red gate by deleting the assertion, weakening the claim, accepting a hidden
fallback, or excluding the affected surface without a documented product decision.

## Dependency and Nornyx changes

Keep runtime dependencies exact. Any Nornyx or adapter change must follow the compatibility upgrade
procedure, record exact release and audited-source bindings, regenerate `uv.lock`, verify all
contracts/artifacts/locks, execute adapter conformance and every learner gate, and review assurance
language independently. A moving `main` commit must not be presented as a released package.

For other dependencies, explain why the version is selected, regenerate the appropriate frozen
lock, review transitive changes, and run the affected source and container builds. Do not mix a
large dependency refresh into an unrelated curriculum or visual change.

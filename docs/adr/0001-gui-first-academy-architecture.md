# ADR 0001: GUI-first academy architecture

- **Status:** Accepted
- **Date:** 2026-08-07
- **Decision owners:** nornyx-lab maintainers
- **Scope:** learner experience, curriculum execution, persistence, and Nornyx integration

## Context

The original repository is a technically strong collection of 25 Python labs, but its learner
contract is a command-line application, generated Jupyter notebooks, direct filesystem edits,
and fixed pytest checks. That surface cannot satisfy a beginner who must learn, experiment,
receive meaningful assessment, and track progress without a terminal, notebook, Python, YAML,
or filesystem navigation.

The audit also found architectural risks that a browser product must not inherit:

- narrative, execution, filesystem mutation, and Rich rendering are coupled in `lab.py`;
- `ctx.results` is an unvalidated dictionary rather than a scenario-result contract;
- the existing checks are repository regressions, not learner assessments;
- some labs mutate shared committed fixtures, which is unsafe for concurrent or interrupted runs;
- progress is a single `{lab_id: status}` JSON object;
- the current curriculum assumes governance knowledge before it teaches AI and agent mechanics;
- several advanced labs promise execution that is currently prose or a smaller scripted example;
- the learner-facing surfaces can imply stronger evidence or adapter coverage than the executed
  path supports.

The deterministic planner, inert Northstar business actions, attempt/completion ledger, real
`.nyx` contracts, generated artifacts and locks, Nornyx authorizer, evidence recorder, adapter
fixtures, and many regression tests remain valuable and should not be discarded.

## Decision

### Product topology

The academy is a local-first web application with four explicit boundaries:

1. **React + TypeScript browser client** for navigation, lessons, diagrams, forms, visual
   builders, assessment, and progress.
2. **FastAPI + Pydantic service** exposing versioned structured JSON APIs. The service never
   invokes the legacy `nornyx-lab` CLI or parses ANSI output.
3. **Python curriculum and scenario domain** that reuses the deterministic planner, ledger,
   Northstar callables, real Nornyx SPI, and adapter APIs behind typed results.
4. **Learner-record port** with a local SQLite implementation. A stable repository interface
   keeps later multi-user persistence from requiring a curriculum-engine rewrite.

The production service serves the built browser client from the same origin. Vite provides the
development server and proxies `/api` to FastAPI. Docker uses a multi-stage build.

### Curriculum model

Curriculum content, executable scenarios, learner assessment, presentation, and persistence are
separate concerns:

- structured catalog data defines modules, prerequisites, concepts, learning paths, expected
  outcomes, completion rules, and GUI interaction types;
- the six AI-engineering foundation modules precede the migrated governance curriculum;
- every original lab is mapped to a migrated, superseding, split, rewritten, or deliberately
  retired learner experience;
- legacy pytest checks remain regression gates only;
- learner completion requires an executable result and/or a scored, meaningful assessment;
- progress stores attempts, scores, concepts mastered or needing review, and activity timestamps.

### Scenario result contract

Every executable scenario returns schema-validated structures for:

- planner/model input and proposed actions;
- identity, capability, resource, source and target trust zones;
- policy declaration, evaluated rule or gate, decision code and effect;
- approval assertion and validation state;
- enforcement point and coverage surface;
- tool attempts and completions;
- ordered evidence events, validation findings, and missing evidence;
- claims that are supported, unsupported, or indeterminate;
- assessment and completion state.

For business side effects, `0 attempts / 0 completions`, `1 / 0`, `1 / 1`, and unknown evidence
remain distinct states. Counters settle side-effect claims; they do not replace diagnostic,
integrity, schema, provenance, or coverage evidence.

### Execution isolation

Legacy labs that read or write repository-relative files run only in a per-run temporary
workspace. The runner copies the minimal repository fixture set, points dynamic repository-root
resolution at that copy for the duration of the run, and deletes it afterwards. Browser sessions
never edit committed contracts, locks, artifacts, or another learner's workspace.

New scenarios use immutable definitions and in-memory inert ledgers. No default training action
sends email, transfers money, publishes content, pushes code, invokes an MCP server, installs an
untrusted package, or performs an external business action.

### Nornyx integration and compatibility

Nornyx remains the source of truth for contract parsing/checking, generated controls, locks,
authorization decisions, approval assertions, evidence construction and validation, and adapter
behavior. The service calls the published Python SPI where it exists and uses the Nornyx CLI only
as an internal design-time interface for operations not exposed as an equivalent stable API.

The runtime pins released, mutually compatible Nornyx and adapter versions. Each release also
records the exact audited commit on authoritative `main` and its delta from the runtime tag. An
unreleased `main` commit is not silently presented as a published package version. Upgrades must
regenerate and compare artifacts, diagnostics, locks, scenarios, adapter conformance, coverage,
and learner explanations before changing the pin.

The UI distinguishes:

- a declaration from an evaluated control;
- a direct approval-assertion validation from a gated zone-crossing decision;
- an authorizer decision from adapter enforcement and tool observation;
- generated-control binding from proof of runtime use;
- evidence integrity from evidence completeness or event truth;
- Tier 2 cooperative in-process coverage from independent enforcement.

### Offline and optional live-model modes

The deterministic susceptible planner is the default and is always available without a key or
network. It is labeled as a pedagogical fixture, not an LLM.

Optional live-model configuration is entered in the GUI. Secrets remain process-memory-only,
masked in responses, never written to the learner database, never logged, and are cleared on
restart. Live mode is visibly different, requires explicit opt-in, displays the exact proposed
plan, and never changes a Nornyx decision for an identical authorization request. Because a live
model can propose a different plan, the product never describes whole-run effects as invariant.

### Information architecture

The primary routes are:

- home and orientation;
- five-minute governed/ungoverned demonstration;
- audience learning paths;
- curriculum browser and lesson viewer;
- learner dashboard;
- scenario and failure-injection workbench;
- contract explorer and guided builder;
- agent/trust-zone and enforcement graphs;
- approval simulator;
- evidence and diagnostics explorers;
- assessments;
- capstone workspace;
- settings and live-model configuration;
- Nornyx scope and honest-boundaries reference.

All primary operations are reachable by keyboard. Desktop and tablet are first-class; mobile
retains readable content and core controls without pretending dense graph editing is ideal on a
small screen.

## Alternatives considered

### Keep the CLI and add a browser terminal

Rejected. It preserves the exact usability failure and turns terminal text into the product API.

### Static documentation site with embedded screenshots

Rejected. It cannot execute, break, compare, validate, assess, or persist real scenarios.

### Spawn the existing CLI and scrape output

Rejected. ANSI prose is not a stable contract, cannot express indeterminate evidence honestly,
and would couple the UI to presentation formatting.

### Rewrite the domain in TypeScript

Rejected. It would duplicate Nornyx semantics, discard verified Python assets, and create two
implementations that could diverge.

### Run legacy labs against the shared checkout

Rejected. Several labs mutate committed fixtures and are not interruption- or concurrency-safe.

### Pin an unreleased moving `main` branch

Rejected as the default runtime policy. The academy audits `main`, records the exact commit and
known delta, and adopts new behavior through an explicit compatibility upgrade.

## Consequences

Positive consequences:

- beginners can complete the product without a developer toolchain;
- professionals retain access to real contracts, diagnostics, controls, locks, evidence, and
  adapter behavior;
- the UI renders stable structures rather than terminal formatting;
- progress and assessment become meaningful and extensible;
- old executable assets remain regression-tested while unsafe mutations are isolated;
- assurance language is centralized and testable.

Costs and trade-offs:

- the repository now owns a browser toolchain as well as Python;
- authoring requires schema validation and content coverage checks;
- per-run fixture isolation adds startup cost to legacy lab execution;
- exact YAML comments and formatting cannot round-trip through Nornyx's canonical dictionary
  formatter, so the source view must state that limitation;
- local single-user persistence is not authentication or tenancy isolation.

## Assurance boundary

The academy is a training platform. Its default business effects are inert simulations. Nornyx
declares, checks, composes, generates, locks, decides, and validates supplied evidence; it does
not orchestrate agents, execute tools, authenticate actors, attest runtime truth, make a wrapped
path unavoidable, or govern this academy merely because the academy uses it.

The initial runtime demonstrations are cooperative in-process surfaces and support Tier 2 claims
at most, scoped to the named path and evidence producer. Unknown or unobserved paths remain
unknown. No page may claim Tier 3 without an independently enforced, unavoidable boundary and
independent attestation that the scenario actually exercises.

# Baseline audit

**Audited repository commit:** `f76447b258661584540012d4b060fd00ad08380e`  
**Audit date:** 2026-08-07  
**Purpose:** establish the factual pre-GUI baseline before product decisions or migration.

## Verification result

The pre-transformation baseline was healthy and worth preserving:

| Gate | Baseline result |
|---|---|
| Environment doctor | Pass: Python 3.12.10, Nornyx 1.11.0, adapters 0.3.0, SPI 1.2, 25 labs |
| Contract/artifact/lock drift | Pass: `scripts/build_contracts.py --verify` |
| Serial repository suite | 278 passed, 0 failed, 0 skipped in 935.732 seconds |
| Adapter conformance with CI environment | 33 cases: 32 pass, 1 explicitly not representable, 0 blocked |
| Ruff lint | Pass |
| Ruff format check | Pass |

The baseline suite deliberately runs serially. Several labs temporarily mutate shared fixtures,
and parallel execution against the checkout is not safe. The academy runner therefore uses a
per-execution temporary copy rather than weakening the existing serial regression guarantee.

CrewAI’s first import can initialize tracing and attempt process execution. Conformance is only
stable when these controls are set before any CrewAI import:

```text
CREWAI_DISABLE_TELEMETRY=true
CREWAI_TRACING_ENABLED=false
CREWAI_TESTING=true
OTEL_SDK_DISABLED=true
PYTHONIOENCODING=utf-8
```

They are set at process startup in the academy service, Docker image, and CI.

## Inventory

- 25 labs, 695 estimated minutes;
- 4 beginner, 10 intermediate, and 11 advanced labs;
- 41 mapped book chapters;
- 158 concepts in original lab metadata;
- a strict linear prerequisite chain;
- 176 lab-local regression checks plus repository tests;
- two real agentic-network contracts (`atlas` and `ledger`), their generated controls,
  governance evidence, profile locks, and network locks;
- deterministic and optional live planners;
- an inert attempt/completion ledger and Northstar business-action functions;
- real Nornyx authorization, approval, evidence, generation, integrity, and adapter examples;
- CrewAI and LangGraph integrations plus adapter conformance;
- generated notebooks and documentation;
- Rich/Typer CLI progress stored as a small JSON status map.

## Preserve

The audit classified these assets as strong, factual, and reusable:

- deterministic susceptible planner;
- exact action plan reused across governed and ungoverned comparisons;
- inert Northstar actions;
- separate attempt and completion counters;
- pinned time and subject revision;
- real `.nyx` source, artifacts, locks, and diagnostics;
- Nornyx Authorizer and EvidenceRecorder usage;
- known negative controls and bypass demonstrations;
- framework adapter tests and the no-silent-skip conformance rule;
- byte-deterministic generation and drift checks;
- honest Tier 2/cooperative-coverage statements;
- regression tests encoding valid behavior.

## Adapt behind service boundaries

These were correct but unsuitable as direct learner interfaces:

| Baseline asset | GUI adaptation |
|---|---|
| `lab.py` narration and execution | Captured into typed content blocks and results in an isolated workspace |
| CLI Nornyx calls | Stable Python APIs where available; structured internal tool result otherwise; no ANSI scraping |
| YAML mutation exercises | Guided semantic form operations against an isolated canonical copy |
| Rich decision/counter tables | Pydantic decision, trace, counter, finding, evidence, and claim models |
| Notebook/README lesson text | Progressive-disclosure browser lesson content |
| CrewAI/LangGraph examples | Explicit adapter availability and exact supported-surface labels |
| Original checks | Retained as engineering regressions, not learner assessment |

## Rewrite or replace

The audit found product gaps that could not be solved with presentation changes:

- the primary learner journey required a shell, filesystem, YAML, or notebook;
- `run(ctx)` coupled narration, execution, state, and presentation;
- results were untyped dictionaries;
- the old progress record only stored a coarse status;
- running pytest was treated as assessment even though tests reconstructed fixed scenarios;
- some generated documentation incorrectly implied checks asserted recorded context values;
- labs 11 and 15 could mutate committed artifacts during their exercises;
- Lab 19 promised retry, loop, parallel, interrupt, and resume coverage but executed a smaller
  linear graph;
- Lab 22 was mostly narrative and did not execute a realistic multi-agent workflow;
- Lab 23 could imply a broader CrewAI surface from raw authorizer evidence and used placeholder
  standards mapping;
- Lab 24 was a fixed scripted walkthrough rather than a learner-configurable capstone;
- the strict prerequisite chain did not serve distinct beginner, engineering, architecture,
  governance, and practitioner audiences;
- AI/LLM/software foundations were insufficient before advanced governance concepts.

Those gaps led to six new foundation modules, seven learning paths, a data-driven assessment
engine, SQLite learner record, schema-validated scenario API, contract workbench, executable
multi-agent capstone, and browser UI. The precise disposition of every lab is in
[MIGRATION_MAP.md](MIGRATION_MAP.md).

## Platform constraints retained

- `LAB_AS_OF=2026-06-01T12:00:00Z` remains inside the declared approval window
  (`2026-06-01` through `2026-06-08`).
- `LAB_SUBJECT_REVISION=git:5eed1e55c0ffee1abadcafe0ddba11ed15ea5e11` preserves byte-stable
  artifact and evidence bindings.
- UTF-8 output remains explicit on Windows.
- Contract generation remains LF- and byte-sensitive.
- Browser legacy execution never runs against the shared checkout.
- Optional frameworks must be installed in full CI; absence is an explicit unavailable result,
  never a green fallback.

## Decision

The baseline was not discarded. It became the verified domain and regression layer beneath a
new GUI-first product boundary. The rationale and consequences are recorded in
[ADR 0001](adr/0001-gui-first-academy-architecture.md).

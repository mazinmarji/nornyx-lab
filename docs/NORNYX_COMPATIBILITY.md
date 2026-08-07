# Nornyx compatibility and upgrade policy

## Runtime baseline

The academy runs released, mutually compatible packages:

| Component | Pin | Release binding |
|---|---:|---|
| Nornyx | `1.11.0` | tag `v1.11.0`, commit `dca0ac676ff7a30a5b97ac6d0b4cf58c6fc07c2f` |
| Nornyx agentic adapters | `0.3.0` | tag commit `a02f7682a8f67e64ef5a4f3b77a01e733e3e8e04` |
| Agentic SPI | `1.2` | required by the adapter baseline |
| Agentic-network module | `0.2.0` | recorded in generated manifests/locks |
| CrewAI | `1.15.4` | adapter-supported cooperative synchronous tool surface |
| LangGraph | `1.2.2` | adapter-supported synchronous `StateGraph` node surface |

Pins live in `pyproject.toml`, the full transitive resolution lives in `uv.lock`, and the
machine-readable compatibility record lives in
`src/nornyx_lab/academy/content/compatibility.json`. Docker and CI consume the frozen lock.

## Why released tags—not moving main

The authoritative Nornyx source was also audited at the latest `main` commit available on
2026-08-06:

```text
8d00029e6d3486a6aa348e1e113f7c6f7e6ebe1a
```

That commit was 52 commits after `v1.11.0` while package metadata still reported `1.11.0`. The
observed main-only delta was limited to checker/CLI policy diagnostics:

- `UNKNOWN_POLICY_RULE` checker warning;
- evaluated harness deny-rule vocabulary;
- `nornyx check --strict`.

Authorization, approval, evidence, profiles, artifact generation, and lock APIs used by the
academy were unchanged in the audited delta. The academy records that fact but does not claim
unreleased checker behavior at runtime. A moving commit is not a reproducible package contract.

## API use and semantic boundaries

The application uses published APIs where available:

- `load_nyx`, `check_document`, and `has_errors` for source semantics;
- `registry_for_contract`, `compose_document_governance`, and
  `evaluate_document_governance` for profile/governance composition;
- `render_agentic_network_artifacts` for generated controls;
- agentic-network lock build/write/load/verify APIs;
- `load_authorizer` plus typed request models for decisions;
- `EvidenceRecorder` for occurrence evidence and validation.

Diagnostics expose level, code, message, and semantic path. The released API does not provide
source line/column locations, so the browser must not invent them. Canonical formatting uses
YAML safe dumping and does not preserve comments or original stylistic formatting; workbench
results state this limitation.

Free-text policy declarations are not automatically evaluated by the agentic Authorizer. The
academy never presents declarations such as `autonomous_approval` or
`undeclared_cross_zone_transition` as runtime controls unless a real evaluated request/gate
supports that statement.

## Approval boundary

These released-runtime facts are enforced in lessons and tests:

- `CapabilityRequest` evaluates current holdings and has no approval field;
- `ApprovalRequest` validates an assertion but does not mutate or unlock an Authorizer;
- the combined runtime path demonstrated here is a gated `ZoneCrossingRequest` carrying an
  `ApprovalAssertion`;
- a missing assertion returns approval-required; a valid bound assertion may allow the crossing;
- assertion validity does not authenticate the human approver by itself.

## Adapter compatibility

### CrewAI

The adapter covers synchronous `BaseTool._run` reached through native kickoff. Async tools,
agents, tasks, delegation, and handoff internals are not implicitly covered. CrewAI may retry a
denied call; the business counter can remain `0/0` while duplicate occurrence evidence fails
replay validation. The exact occurrence stream—not a blanket “CrewAI governed” claim—settles the
lesson.

### LangGraph

The adapter covers synchronous `StateGraph` nodes with occurrence-aware metadata. The public
metadata model can represent retry, loop, parallel, interrupt, and resume identity. Async or
distributed execution, subgraphs, and `ToolNode` internals are not implicitly intercepted.

Both are Tier 2 cooperative, declared surfaces only. Conformance inventory is a scoped coverage
result, not proof that every framework path is unavoidable.

## Upgrade procedure

Upgrades are intentional compatibility work, not dependency-bot merges.

1. Fetch the authoritative Nornyx and adapter repositories and record exact candidate commits,
   tags, dates, and package metadata.
2. Read release notes and diff from the current tag, focusing on schemas, profiles, diagnostics,
   generation, locks, authorizer request/decision models, evidence, and adapters.
3. Create a dedicated compatibility branch; change pins and regenerate `uv.lock`.
4. Run the environment doctor with CrewAI telemetry disabled before import.
5. Rebuild contracts in scratch and run `scripts/build_contracts.py --verify`; review every byte
   and semantic diagnostic change.
6. Run unit/API/scenario tests, all 25 structured lab migrations, the full legacy suite, and
   adapter conformance with no silent skip.
7. Run frontend contract/component tests and the complete fresh-learner browser journey.
8. Inspect A/B decision codes, approval states, evidence schemas, occurrence ids, and counter
   claims manually; update explanations only to match observed released behavior.
9. Update the machine-readable compatibility record, this document, assurance language, and any
   screenshots whose structured result changed.
10. Build the Docker image from frozen locks on Linux and exercise source deployment on Windows.
11. Require review from a maintainer who did not perform the upgrade.

An upgrade must fail if a framework disappears, a test skips silently, artifacts drift without
review, a diagnostic is reworded into an invented capability, or a stronger assurance statement
appears without a stronger enforcement architecture.

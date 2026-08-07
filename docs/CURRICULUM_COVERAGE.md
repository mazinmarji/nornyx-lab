# Curriculum coverage

The academy contains 31 modules: six new foundations (`F0`–`F5`) and a disposition for every
original lab (`00`–`24`). This page is a human-readable coverage projection. The canonical
machine-readable sources are:

- [`modules.json`](../src/nornyx_lab/academy/content/modules.json): foundation content, legacy
  enrichment, interactions, scenario ids, and migration classifications;
- every [`lab.toml`](../labs): original objectives, concepts, prerequisites, difficulty, and time;
- [`paths.json`](../src/nornyx_lab/academy/content/paths.json): audience sequences and completion
  criteria;
- [`assessments.json`](../src/nornyx_lab/academy/content/assessments.json): scored prompts,
  options, explanations, and concept signals.

The service merges these sources into `/api/v1/catalog` and rejects missing or unknown legacy
entries. Every module requires executable success and a passing scored assessment. Original
pytest checks are regression gates, not learner assessments.

## Path legend

| Code | Learning path |
|---|---|
| **B** | `beginner` — Beginner: AI assistant to governed agent |
| **D** | `developer` — Developer: building governed AI software |
| **E** | `agent-engineer` — Agent engineer: tools, workflows, and multi-agent systems |
| **A** | `architect` — Architect: trust zones, authority, and runtime boundaries |
| **G** | `governance-risk` — Governance and risk: policy, evidence, assurance, and audit |
| **N** | `nornyx-practitioner` — Nornyx practitioner: contracts to runtime evidence |
| **C** | `complete` — Complete curriculum: beginner to professional |

The Paths screen supplies each path’s prerequisites, computed effort, full concept set, progress,
outcomes, and completion rule. Learners may change paths without changing or losing the local
record.

## Module-to-execution and assessment matrix

| Module and concept themes | Executable GUI interaction / scenario | Assessment | Paths | Expected outcome |
|---|---|---|---|---|
| **F0 — Five-minute governed-agent demonstration** · assistant, agent, prompt injection, PDP/PEP, counters, evidence, assurance | `governed-ungoverned-demo` · `demo.untrusted_publish_ab`; one captured plan runs through ungoverned `1/1` and governed approval-required `0/0` paths | `assessment.F0` · assurance correction | B D E A G N C | Distinguish message from side effect, interpret counters, and state a named cooperative claim plus limitation. |
| **F1 — Models, software, and responsibility boundaries** · LLMs, tokens, probabilistic generation, hallucination, deterministic code | `model-variability-lab` · `foundation.model_variability`; repeated seeded local samples and a responsibility-boundary sorter | `assessment.F1` · scenario prediction | B D E A G C | Explain an LLM plainly, contrast variable output with deterministic invariants, and place validation at the application boundary. |
| **F2 — Prompts, context, and structured outputs** · prompt hierarchy, context budget, retrieval, taint, schema validation | `context-composer` · `foundation.context_contract`; compose labeled context, reserve output budget, and validate model-shaped JSON | `assessment.F2` · ordering | B D E A G C | Separate instruction from data, explain bounded context, and validate structured output before routing it. |
| **F3 — Assistants, tools, and side effects** · function calling, reachability, authorization, attempt/completion | `tool-side-effect-simulator` · `foundation.tool_side_effect`; compare no tool, least privilege, and over-privileged inert callable paths | `assessment.F3` · evidence interpretation | B D E A G N C | Trace proposal-to-effect, distinguish reachability from authority, and prefer observed counters over transcript claims. |
| **F4 — How agents run** · loop, plan, workflow, memory, retry, handoff, parallel and multi-agent execution | `agent-runtime-graph` · `foundation.agent_runtime`; deterministic linear/retry/handoff/parallel timelines with occurrence and attempt ids | `assessment.F4` · ordering | B D E G C | Trace execution patterns, distinguish retry from new work, and separate model, framework, application, and governance roles. |
| **F5 — Engineering reliable AI applications** · evaluations, nondeterministic testing, observability, secure integration, delivery gates | `evaluation-workbench` · `foundation.ai_delivery_eval`; repair schema, authorization, timeout, idempotency, telemetry, and no-hidden-skip cases | `assessment.F5` · policy repair | B D E A G N C | Test invariants rather than exact prose, fail closed around tools, and reject missing checks or silent fallback. |
| **00 — From assistant to agent** · agentic execution, side-effect ledger, reachability, instruction/data confusion | `assistant-agent-simulator` · `lab00.instruction_data_confusion`; isolated original scenario returned as structured blocks and counters | `assessment.00` · scenario prediction | B D E G C | Tell response generation from tool authority and refusal text from actual prevention. |
| **01 — The governance gap** · governance debt, policy/configuration/adapter drift, single source | `control-drift-diff` · `lab01.control_drift` | `assessment.01` · ordering | B D A G C | Find inconsistent controls and order a checked source-to-generated-control workflow. |
| **02 — What governance can and cannot guarantee** · assertion layers, integrity, authenticity, completeness, fail behavior | `claim-layer-sorter` · `lab02.assertion_layers` | `assessment.02` · evidence interpretation | B A G C | Separate five claim layers and refuse to infer completeness or prevention from integrity alone. |
| **03 — PDP, PEP, and assurance vocabulary** · decision versus enforcement, design/runtime, cooperative/independent | `pdp-pep-wiring-canvas` · `lab03.pdp_pep_wiring` | `assessment.03` · identify the bypass | B D E A G N C | Place the enforcement point on every claimed effect path and scope assurance to that surface. |
| **04 — Identity, capability, and authority** · framework binding, least privilege, delegation, handoff, confused deputy | `identity-authority-graph` · `lab04.identity_authority_graph` | `assessment.04` · identify the bypass | B D E A G N C | Resolve governance identities and prevent delegation from manufacturing authority. |
| **05 — Trust zones and prompt injection** · origin/authority/taint, share rules, ingress/egress gates | `trust-zone-injection` · `lab05.trust_zone_injection`; shares the real Atlas A/B domain used by F0 | `assessment.05` · policy repair | B D E A G N C | Preserve research while enforcing the high-consequence public crossing despite a fooled planner. |
| **06 — Policy semantics** · three-valued decisions, default deny, total and deterministic evaluation | `decision-matrix` · `lab06.decision_matrix` | `assessment.06` · scenario prediction | B D E A G N C | Predict allow, deny, and approval-required from explicit request, time, and revision inputs. |
| **07 — Composition and provenance** · merge/override/narrow, monotonicity, effective governance, profiles lock | `composition-layer-view` · `lab07.composition_provenance` | `assessment.07` · policy repair | E A G N C | Trace every effective restriction to its source and reject silent widening. |
| **08 — Approvals** · action/evidence/revision/time binding, human accountability, maker-checker | `approval-simulator` · `lab08.approval_mutations`; also `/approvals` | `assessment.08` · evidence interpretation | B D E A G N C | Diagnose bounded approval failures without treating validation as authentication or a permanent unlock. |
| **09 — Enforcement models** · placement, fail-open/closed, bounded fallback, blast radius | `enforcement-failure-lab` · `lab09.enforcement_failure`; also `/workbench` | `assessment.09` · scenario prediction | B D E A G N C | Select failure semantics deliberately and prove pre-call prevention with the right counters. |
| **10 — Evidence is not logging** · producer, binding fields, supplied/observed, data minimization | `evidence-explorer` · `lab10.evidence_contract`; also `/evidence` | `assessment.10` · evidence interpretation | B D E A G N C | Build and inspect bound evidence while keeping conformance, truth, and completeness distinct. |
| **11 — Digests, locks, ordering, and replay** · content addressing, multi-way binding, occurrence and replay | `lock-replay-workbench` · `lab11.lock_replay`; all tampering occurs in an isolated copy | `assessment.11` · ordering | E A G N C | Verify locks and classify mission, operation, occurrence, and multiple attempts without mutating source fixtures. |
| **12 — Assurance tiers** · adversary, consequence, claim boundary, self-reported evidence, tier inflation | `assurance-claim-editor` · `lab12.surface_assurance` | `assessment.12` · assurance correction | B D E A G N C | Rewrite an inflated claim with its exact surface, mechanism, producer, version, bypass, and falsifier. |
| **13 — Bypass and coverage** · wrapped/unsupported/unwrapped, negative controls, five-test rule | `bypass-explorer` · `lab13.coverage_bypass` | `assessment.13` · identify the bypass | D E A G N C | Inventory real effect paths and retain a direct-call negative control rather than claiming wrapper-wide coverage. |
| **14 — First `.nyx` contract** · closed contract blocks, contexts, deny/require, diagnostics, version axes | `visual-contract-builder` · `lab14.visual_contract_builder`; `/contracts`, `/builder`, `/diagnostics` use real Nornyx APIs | `assessment.14` · policy repair | B D E A G N C | Make guided semantic edits while preserving `.nyx` as the authoritative checked representation. |
| **15 — Profiles, modules, and locks** · effective governance, lock diagnostics, four controls/four questions | `profile-lock-workbench` · `lab15.profile_lock_binding`; all lock breaking occurs in an isolated copy | `assessment.15` · assurance correction | E A G N C | Trace profile provenance and state exactly which bytes a valid network lock does and does not bind. |
| **16 — Authorization interface** · assured construction, detached state, one interpretation, typed requests | `authorization-request-workbench` · `lab16.assured_authorizer` | `assessment.16` · identify the bypass | D E A N C | Load one lock-verified Authorizer and avoid split-brain interpretations across consumers. |
| **17 — Evidence architecture and drift** · occurrence/attempt rules, resume, byte determinism, exit-code interface | `occurrence-drift-timeline` · `lab17.occurrence_drift` | `assessment.17` · evidence interpretation | D E A G N C | Distinguish retry, repeat, duplicate, and resume identities, then enforce a deterministic artifact drift gate. |
| **18 — CrewAI adapter** · binding, protected sequence, injected dependencies, pinned cooperative coverage | `crewai-adapter-lab` · `lab18.crewai_governed_tool`; real pinned synchronous native-kickoff tool path | `assessment.18` · assurance correction | D E A N C | Exercise allow/deny and evidence on supported `BaseTool._run` while naming async, delegation, handoff, and direct-call gaps. |
| **19 — LangGraph occurrence suite** · authorization denial, node invocation, retry, loop, parallel, interrupt, cumulative resume, unwrapped/unsupported coverage | `langgraph-occurrence-suite` · `lab19.langgraph_occurrence_suite`; real pinned graphs return a Nornyx denial with `0/0` tool counters, retry attempts 1–3, distinct loop/parallel occurrences, interrupt/resume attempts 1–2, valid evidence, an executed unwrapped topology probe, and rejected async construction | `assessment.19` · evidence interpretation | E A N C | Interpret public runtime occurrence metadata while keeping raw runtime ids, host/operator continuity, async/distributed/subgraph/`ToolNode` paths, and whole-graph coverage outside the claim. |
| **20 — Conformance, external enforcement, supply chain** · runtime/static conformance, dual evidence, projection drift, package claims | `conformance-supply-chain-lab` · `lab20.conformance_supply_chain` | `assessment.20` · identify the bypass | D E A G N C | Separate adapter conformance, independent-PEP requirements, and inert static package mismatch findings. |
| **21 — Authoring and CI** · three diffs, gate set, zero-skip detection, trusted publishing | `authoring-ci-pipeline` · `lab21.authoring_ci_pipeline` | `assessment.21` · ordering | D G N C | Move authoritative source through check, review, generation, lock, tests, conformance, and publish without hidden green lanes. |
| **22 — Forge multi-agent delivery** · distinct maker/checker identities, delegation/handoff, generated candidate controls/lock, human release approval, incident signals | `forge-release-network` · `lab22.forge_release_network`; ephemeral Forge contract executes author, delegated tests, independent review, approved handoff/merge, gated release, and closure with negative controls | `assessment.22` · policy repair | D E A G N C | Execute bounded author, reviewer, release-agent, approval-router, and separate human-owner responsibilities and expose failed-test, missing-approval, unauthorized-merge, and direct-bypass paths. |
| **23 — Risk, standards, and audit** · threat/residual-risk matrix, educational standards mapping, evidence limits, supported/unsupported/indeterminate claim register | `assurance-audit-workbench` · `lab23.assurance_workbench`; actual allow, deny, approval-required, revision-mismatch, direct-bypass, and indeterminate-evidence rows feed three explicitly non-conformity mappings | `assessment.23` · assurance correction | A G N C | Derive checkable records from actual decisions/counters/evidence; retain mechanism, artifact, surface, gap, owner, cadence, falsifier, and non-certification status without compliance washing. |
| **24 — Northstar capstone** · system composition, multiple identities, failure injection, integrity, evidence, bypass, residual risk | `capstone-workspace` · `lab24.northstar_workspace`; configurable `/capstone` run with six controlled failures | `assessment.24` · assurance correction, 85% | N C | Configure, run, break, validate, and defend a multi-agent remediation workflow with a scoped Tier 2 ceiling and a documented real bypass. |

## Required topic-family coverage

The matrices below name a primary executable home for every required topic. Other modules reinforce
many of them; the module matrix and machine-readable concept lists provide the complete many-to-many
mapping.

### AI software-development foundations

| Required topic | Primary modules and executable treatment |
|---|---|
| AI-assisted development | F5 evaluation/delivery workbench; 21 authoring pipeline; 22 multi-agent delivery |
| Model limitations | F1 output variability and responsibility sorting; F2 malformed structured output; F5 invariant tests |
| Prompts and context | F2 context composer; 00 and 05 instruction/data and taint scenarios |
| Testing nondeterministic behavior | F1 repeat samples; F5 invariant-based evaluation rather than exact prose |
| Evaluations | F5 repairable suite; 13 negative controls; 21 zero-skip release gate |
| Tool use | F3 tool attachment; 00 side-effect transition; 18 supported CrewAI tool surface |
| Structured outputs | F2 schema and budget validation; F5 schema-drift case |
| Secure integration | F3 least privilege; F5 authorization/timeouts; 18/20 adapter and supply-chain boundaries |
| Observability | F5 required telemetry; 10 evidence explorer; 17 occurrence identities |
| Model and software boundaries | F1 responsibility map; F3 application-owned tool; 00 message-versus-effect proof |
| Failure handling | F5 bounded repair cases; 09 fail-open/closed/bounded; 19 retry/interrupt/resume |
| Software delivery with AI agents | 21 CI lifecycle; 22 Forge separation of duties; 24 capstone workflow |

### Agentic AI

| Required topic | Primary modules and executable treatment |
|---|---|
| Assistants versus agents | F3 and 00 compare text-only and tool-reachable paths |
| Tools and side effects | F3, 00, 05, 09, and 13 use inert attempts/completions |
| Planning | F4 runtime model; 00/05 one captured injected plan |
| Loops | F4 runtime timeline; 17 identity rules; 19 real LangGraph loop visit |
| Retries | F4 multiple attempts; 11/17 evidence rules; 19 adapter retry |
| Memory | F4 framework responsibility map and bounded runtime state |
| Workflows | F4 patterns; 19 graph; 22 delivery network; 24 remediation workflow |
| Handoffs | F4 handoff timeline; 04 authority graph; 22 and 24 distinct-role transitions |
| Multi-agent systems | F4 responsibility foundations; 22 separation-of-duties network; 24 capstone |
| Framework integration | F4 responsibility boundary; 18 CrewAI; 19 LangGraph; 20 conformance |
| Trust boundaries | 05 taint/zones; 09 enforcement placement; 14 contract view; 24 capstone crossings |
| Prompt injection | F0/00 A/B; F2 authority labeling; 05 boundary control; 24 controlled failure |
| Identity and authority | 04 graph; 06 typed decision inputs; 16 Authorizer; 22/24 role separation |
| Runtime enforcement | 03 PDP/PEP; 05 A/B; 09 failures; 13 bypass; 18/19 adapter surfaces |
| Evidence and replay | 10 evidence contract; 11 replay; 17 occurrence architecture; 19 resume; 24 evidence/bypass |

### Governance foundations

| Required topic | Primary modules and executable treatment |
|---|---|
| Governance gap | 01 drift comparison |
| Policy | 06 deterministic semantics; 07 composition; 14 authoritative contract |
| Control | 01 generated-control alignment; 03 decision/enforcement wiring; 21 release gates |
| Decision | 03 PDP; 06 matrix; 16 typed Authorizer requests |
| Enforcement | 03 PEP; 05 egress gate; 09 failures; 13 bypass |
| Approval | 06 approval-required; 08 mutation simulator; 24 bound approval path |
| Accountability | 08 human/maker-checker; 22 separation of duties; 23 owner/cadence records |
| Separation of duties | 04 delegation authority; 08 maker-checker; 22 Forge; 24 capstone |
| Least privilege | F3/F5 application permissions; 04 capability graph; 22 bounded identities |
| Fail-open versus fail-closed | 02 assertion/failure layer; 09 direct counter comparison |
| Evidence | 02 claim layers; 10 contract/explorer; 11/17 identities; 23 audit package |
| Assurance | F0 claim correction; 12 tiers; 13 coverage; 23/24 claim registers |
| Auditability | 10 ordered events; 17 drift; 21 gates; 23 package construction |
| Governance limitations | F0 and 02 boundaries; 12 tier ceiling; 23 open problems; 24 residual risk |

### Nornyx

| Required topic | Primary modules and executable treatment |
|---|---|
| `.nyx` contract | 14 visual/source/builder round trip |
| Checked source of truth | 01 control alignment; 14 diagnostics; 21 authoring gate |
| Generated artifacts | 01 generation; 14 control view; 15 locks; 17 drift; 21 pipeline |
| Profiles | 07 composition; 15 profile provenance and lock |
| Identities | 04 authority graph; 14 contract elements; 16 typed views |
| Capabilities | 04 holdings/delegation; 05 egress action; 06 request; 14 builder |
| Authority | 04, 08, and 16 distinguish declarations, approval, and Authorizer decisions |
| Trust zones | 05 crossing scenario; 14 contract graph |
| Policies | 06 semantics; 07 composition; 14 authoritative source |
| Composition | 07 provenance; 15 locks; 16 single interpretation |
| Approval requirements | 06 three-valued effect; 08 bound assertions; F0/05 real crossing gate |
| Enforcement boundaries | 03, 05, 09, 13, 18, and 19 name the exact cooperative surface |
| Evidence | 10 recorder/validation; 17 occurrence records; 18/19 adapters; 24 capstone |
| Integrity | 02 dimensions; 11 digest/replay; 15 lock binding |
| Locks | 11 artifact/event exercises; 15 profile/network locks; 16 assured load; 17 drift |
| Drift | 01 distributed controls; 17 byte gate; 21 delivery gate |
| Runtime occurrence identity | 11 hierarchy; 17 retries/resume; 19 framework metadata |
| Adapters | 18, 19, and 20 supported surfaces and conformance |
| CrewAI | 18 pinned synchronous `BaseTool._run` through native kickoff |
| LangGraph | 19 pinned synchronous `StateGraph` node variants |
| Conformance | 20 required runtime suite; CI treats absent frameworks/skips as failure |
| Package governance | 20 inert claim-versus-evidence inspection |
| CI integration | 21 checked source, generation, lock, regression, conformance, and publish sequence |
| Assurance claims | F0, 12, 18, 19, 23, and 24 correct scope and limitations |
| Bypass and coverage | 13 direct negative control; 18/19 unsupported surfaces; 24 real bypass |
| Multi-agent governance | 22 Forge roles; 24 multi-identity capstone |
| Adoption patterns | 23 ownership, cadence, residual risk, and open-problem records |
| Capstone | 24 configured execution, failure injection, evidence validation, bypass, and review |

## Coverage verification rules

A topic is not considered covered by prose alone. Its primary module must have a catalog entry, a
callable scenario that returns the structured API schema, at least one executable assertion, a
scored assessment, and tests for its meaningful positive and negative behavior. Framework topics
also require the exact optional dependency, a required conformance result, and an explicit
unsupported/unwrapped inventory. These rules are part of the contributor definition of done and
the CI workflow.

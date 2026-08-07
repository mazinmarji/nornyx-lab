# Legacy-lab migration map

This map accounts for every original lab. It is a product migration record, not a claim that
renaming a legacy script made it browser-native. The canonical authored metadata lives in
[`modules.json`](../src/nornyx_lab/academy/content/modules.json); the original objectives and
concept vocabulary remain in each `labs/*/lab.toml` file.

No lab was retired. All 25 retain a serial regression path and a structured learner path. New
foundation modules `F0`–`F5` teach the AI and software concepts that the original sequence
assumed. A migrated module is complete only after a successful executable run and its scored GUI
assessment; opening a page is never completion.

## Migration mechanics shared by all legacy labs

- The browser calls the versioned FastAPI service and renders Pydantic data. It never starts the
  legacy CLI, scrapes ANSI output, or shows a browser terminal.
- The compatibility runner copies the minimum lab, contract, and script fixtures into a fresh
  temporary workspace for every run. Repository-root resolution is redirected only for that run,
  local paths are redacted, and the copy is deleted afterwards.
- This isolation is mandatory for Labs 11 and 15, whose teaching exercises intentionally tamper
  with artifacts or locks. They never mutate the checkout, another run, or committed evidence.
- Original `checks.py` files remain engineering regressions. Learner assessment comes from
  [`assessments.json`](../src/nornyx_lab/academy/content/assessments.json) and returns immediate
  explanatory feedback in the GUI.
- The default planner and every Northstar business action are inert and local. An observed `1/1`
  means an inert training callable completed, not that email, publication, payment, deployment,
  or another external business action occurred.
- Optional framework absence is returned as **unavailable**, never pass. CI installs both
  framework extras, requires conformance, and fails on any pytest skip.

## Complete disposition

The interaction name and scenario id below are stable catalog identifiers. “Preserved” means the
verified domain asset or concept remains beneath a structured service boundary; it does not imply
that design-time artifacts prove runtime use.

| Lab | Classification | Preserved concepts and assets | GUI interaction and executable scenario | Learner assessment | Rewrite and honest boundary |
|---|---|---|---|---|---|
| **00 — From assistant to agent** | adapt for GUI | Susceptible deterministic planner, instruction/data confusion, attached-tool reachability, inert publish ledger, assistant-versus-agent distinction | `assistant-agent-simulator`; `lab00.instruction_data_confusion`; lesson runner plus the richer `/demo` A/B surface | `assessment.00` · scenario prediction | Removes terminal narration. A proposal is not an attempt; refusal text is not prevention evidence. |
| **01 — The governance gap** | adapt for GUI | Four drift classes, checked source of truth, Atlas source and generated-control comparison | `control-drift-diff`; `lab01.control_drift` | `assessment.01` · ordering | Turns file comparison into a coordinated source-to-control workflow. Generated controls do not prove runtime installation or use. |
| **02 — What governance can and cannot guarantee** | adapt for GUI | Five assertion layers; integrity, authenticity, completeness; fail-open/closed distinctions | `claim-layer-sorter`; `lab02.assertion_layers` | `assessment.02` · evidence interpretation | Learner sorts claims against evidence. A valid digest can bind truncated supplied content without proving completeness or truth. |
| **03 — PDP, PEP, and tier vocabulary** | adapt for GUI | PDP/PEP separation, design/runtime distinction, cooperative/independent enforcement, assurance tiers | `pdp-pep-wiring-canvas`; `lab03.pdp_pep_wiring` | `assessment.03` · identify the bypass | Compares decision-only, enforced, and direct routes. A denial prevents nothing unless a PEP controls the named effect path. |
| **04 — Identity, capability, and authority** | adapt for GUI | Governance identities, framework bindings, capabilities, least privilege, delegation, handoff, confused deputy | `identity-authority-graph`; `lab04.identity_authority_graph` | `assessment.04` · identify the bypass | Visual authority graph replaces role-string reasoning. Delegation may transmit held authority; it cannot create authority. |
| **05 — Trust zones and prompt injection** | preserve behind service API and adapt | Atlas contract, one captured injected plan, context origin/authority/taint, trust-zone crossing, real gated decision, inert counters | `trust-zone-injection`; `lab05.trust_zone_injection`; also powers the polished `/demo` | `assessment.05` · policy repair | Same plan is compared across both paths. The default governed `0/0` supports only the named cooperative wrapper, not all publication paths. |
| **06 — Policy semantics** | adapt for GUI | Typed requests, allow/deny/approval-required domain, default deny, explicit pinned time and revision | `decision-matrix`; `lab06.decision_matrix` | `assessment.06` · scenario prediction | Inputs are controlled fields rather than hidden ambient state. Free-text declarations are not presented as evaluated runtime rules. |
| **07 — Composition and provenance** | adapt for GUI | Profile/module composition, precedence, provenance, monotone narrowing, profile lock | `composition-layer-view`; `lab07.composition_provenance` | `assessment.07` · policy repair | Shows which layer contributed each effective control and rejects widening. A deterministic composition remains a design-time result. |
| **08 — Approvals** | adapt for GUI | Real approval assertion fields, human-role requirement, time window, action/evidence/revision binding, maker-checker | `approval-simulator`; `lab08.approval_mutations`; dedicated `/approvals` route | `assessment.08` · evidence interpretation | GUI mutates one binding at a time. Approval validation does not authenticate the approver or permanently mutate/unlock the Authorizer. |
| **09 — Enforcement failure** | preserve behind service API and adapt | Inert ledger, fail-open, fail-closed, bounded fallback, enforcement-point failure injection | `enforcement-failure-lab`; `lab09.enforcement_failure`; `/workbench` presets | `assessment.09` · scenario prediction | Counters distinguish pre-call prevention (`0/0`) from late failure (`1/0`) and completion (`1/1`). Failure behavior is labeled as application behavior. |
| **10 — Evidence is not logging** | preserve behind service API | Nornyx `EvidenceRecorder`, producer identity, ordered events, contract/revision bindings, findings | `evidence-explorer`; `lab10.evidence_contract`; dedicated `/evidence` route | `assessment.10` · evidence interpretation | Structured event and claim panels replace log prose. Validation establishes conformance of supplied evidence, not event truth or completeness. |
| **11 — Digests, locks, ordering, and replay** | rewrite isolated runner | Generated artifacts, profile/network locks, content digests, mission/operation/occurrence/attempt identities, replay checks | `lock-replay-workbench`; `lab11.lock_replay` | `assessment.11` · ordering | Tamper/reorder/replay operations occur only in a per-run copy and restoration is checked. A valid lock binds named bytes; it does not prove correctness or runtime use. |
| **12 — Assurance tiers** | adapt for GUI | Three-tier rubric, consequence/adversary selection, eight claim questions, surface-scoped assurance | `assurance-claim-editor`; `lab12.surface_assurance` | `assessment.12` · assurance correction | Inflated whole-system claims are rewritten against the returned surface, producer, version, bypass, and falsifier. Cooperative demonstrations remain Tier 2 at most. |
| **13 — Bypass and coverage** | preserve behind service API and adapt | Wrapped/unsupported/unwrapped inventory, direct-call negative control, five-test rule, inert counters | `bypass-explorer`; `lab13.coverage_bypass` | `assessment.13` · identify the bypass | Preserves the real alternate route instead of hiding it. A correct wrapper does not cover an unwrapped direct callable. |
| **14 — First contract** | rewrite as visual builder | Real Atlas/Ledger `.nyx`, closed schema, semantic diagnostics, generated controls, staged repair concepts | `visual-contract-builder`; `lab14.visual_contract_builder`; `/contracts`, `/builder`, and `/diagnostics` | `assessment.14` · policy repair | Guided semantic mutations operate on an isolated canonical copy. `.nyx` remains authoritative; canonical formatting does not promise comment or original-layout round-trip. |
| **15 — Profiles and locks** | rewrite isolated runner | Domain profile/module distinction, composition provenance, `AN_LOCK_*` findings, generated bytes and both lock types | `profile-lock-workbench`; `lab15.profile_lock_binding` | `assessment.15` · assurance correction | Every break/verify cycle uses a temporary copy. Network-lock validity does not prove that a runtime loaded or enforced generated controls. |
| **16 — Authorization interface** | preserve behind service API | `load_authorizer`, lock-verified construction, detached views, typed requests, single-interpretation principle | `authorization-request-workbench`; `lab16.assured_authorizer` | `assessment.16` · identify the bypass | Exposes typed structured requests rather than independent reparsing. A decision still needs an enforcing consumer on the named path. |
| **17 — Evidence architecture** | rewrite into two interactive exercises | Occurrence/attempt identities, retry/repeat/duplicate distinctions, cumulative resume reasoning, byte-deterministic drift gate | `occurrence-drift-timeline`; `lab17.occurrence_drift` | `assessment.17` · evidence interpretation | Separates runtime identity from design-time artifact drift while retaining their binding relationship. Exit codes and diagnostics are interfaces, not assurance by association. |
| **18 — CrewAI adapter** | preserve behind service API and adapt | Pinned CrewAI 1.15.4 native kickoff, synchronous `BaseTool._run` wrapper, Nornyx adapter decisions/evidence, coverage inventory | `crewai-adapter-lab`; `lab18.crewai_governed_tool` | `assessment.18` · assurance correction | Exact cooperative surface only. Async tools, agent/task internals, delegation, handoff, and direct calls are not implicitly covered; a missing extra is unavailable, not green. |
| **19 — LangGraph occurrence behavior** | rewrite executable scenario | Pinned LangGraph 1.2.2 `StateGraph` node adapter, Nornyx adapter 0.3.0, public runtime occurrence metadata, and occurrence-aware evidence | `langgraph-occurrence-suite`; `lab19.langgraph_occurrence_suite`; native graphs execute authorization denial, retry, loop, parallel, and interrupt/resume | `assessment.19` · evidence interpretation | Replaces the original linear-only example. A real wrapped denial yields no business-call attempt or completion; retry produces attempts 1–3 on one occurrence; loop and parallel create distinct occurrences; interrupt/resume preserves one occurrence with attempts 1–2 and cumulative valid evidence. A real unwrapped topology probe executes with zero Nornyx decisions/events, async construction is rejected, and remote/distributed/subgraph/`ToolNode` internals remain unsupported. Missing or incompatible framework pins return unavailable with no modeled fallback. |
| **20 — Conformance, external enforcement, and supply chain** | rewrite and split | Runtime conformance kit, exact coverage inventory, independent-enforcement criteria, inert suspicious-package fixture | `conformance-supply-chain-lab`; `lab20.conformance_supply_chain` | `assessment.20` · identify the bypass | Separates adapter conformance, external-PEP architecture, and static package inspection. The package is never installed or executed; a mismatch is not a safety certification. |
| **21 — Authoring and CI** | rewrite as visual pipeline | Source/effective/generated diffs, check/generate/lock scripts, zero-skip gate, trusted-publishing sequence | `authoring-ci-pipeline`; `lab21.authoring_ci_pipeline`; builder/diagnostic views mirror pipeline states | `assessment.21` · ordering | Visual stages explain the real repository gates. A green pipeline supports only the checks it actually ran and must fail when a required lane is absent. |
| **22 — Multi-agent delivery and operations** | rewrite executable multi-agent workflow | Maker-checker identities, bounded capabilities, delegation/handoff, generated artifacts and lock, policy hierarchy, incident reconstruction | `forge-release-network`; `lab22.forge_release_network`; ephemeral candidate-profile contract runs author → bounded delegated tests → independent review → approved handoff/merge → gated release → closure | `assessment.22` · policy repair | Executes distinct Forge author, reviewer, release agent, approval router, and separate human-owner authority. Negative paths prove author merge denial, failed-test application gating, missing release approval, and an inert direct-call bypass. The generated candidate and lock are temporary and do not prove runtime use outside this run. |
| **23 — Risk, standards, and audit** | rewrite and split | Threat tree, mitigation/residual-risk register, claim register, audit-package structure, adoption/open-problem material | `assurance-audit-workbench`; `lab23.assurance_workbench`; executable allow, denial, approval-required, revision-mismatch, bypass, and indeterminate-evidence rows | `assessment.23` · assurance correction | Derives the matrix from real Nornyx decisions, inert `1/1`/`0/0` counters, validated evidence, and a direct bypass with zero Nornyx decisions. Replaces placeholders with explicit educational mappings to NIST AI RMF 1.0, ISO/IEC 42001:2023, and ISO/IEC 27001:2022; every row names mechanism, artifact, evidence, surface, gap, owner, and cadence and explicitly disclaims certification/conformity. Supported, unsupported, and indeterminate claims retain their falsifiers and gaps. |
| **24 — Northstar capstone** | replace with learner-authored capstone | Northstar/Ledger contract assets, multiple identities and capabilities, approval, handoff, integrity, evidence, bypass, claim and residual-risk review | `capstone-workspace`; `lab24.northstar_workspace`; dedicated `/capstone` configuration and execution API | `assessment.24` · assurance correction; 85% threshold | Replaces the fixed walkthrough with configurable scaffolding and six controlled failures. Framework-neutral execution is real and inert; a CrewAI/LangGraph selection must not be described as runtime execution unless that adapter path actually starts and returns evidence. |

## Replacement verification criteria

Labs 19, 22, 23, and 24 were explicitly identified as insufficient during the baseline audit, so
their catalog names alone cannot satisfy migration. Their dedicated executors and tests verify:

- **19:** separate returned occurrences and attempts for real retry, loop visit, parallel branches,
  incomplete interrupt, and cumulative resume through public LangGraph runtime metadata, plus
  executed unwrapped topology and rejected/unsupported surface controls.
- **22:** distinct author, reviewer, release, approval-router, and human-owner identities execute
  bounded author/test/review/handoff/merge/release steps against an ephemeral checked/locked Forge
  contract; one agent role-playing every job does not pass.
- **23:** threat, residual-risk, standards, claim, and audit records cite actual decisions,
  counters, evidence, and bypass observations; gaps, owners, review cadence, indeterminate paths,
  and non-certification status remain visible.
- **24:** the learner configures the multi-identity workflow and failure, executes both denied and
  approved paths, inspects evidence and a real bypass, then passes the capstone assurance review.

The all-25 structured CI gate verifies compatibility execution and source-workspace isolation. It
does not replace the dedicated behavioral tests above, learner assessments, adapter conformance,
or the browser end-to-end journey.

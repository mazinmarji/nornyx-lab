# Nornyx Academy user guide

Nornyx Academy teaches how AI software becomes an agent, how tools create side effects, and how
governance decisions, enforcement, evidence, and honest assurance fit around that system. You use
the academy entirely in a web browser. No account, API key, terminal, notebook, Python, YAML
editing, or file browsing is required for the default experience.

This guide starts once an operator has opened the academy for you. If the status strip says
**Offline-ready · inert training actions**, executable lessons and local progress are connected.
If it says the service needs attention, pages remain readable but the academy will not invent
scenario results, evidence, or completion.

## Start in five minutes

1. On **Home**, choose **Run the five-minute demo**.
2. Read the short assistant-to-agent explanation. A proposed action is still only a proposal until
   application software gives it a reachable tool.
3. Choose **Run both paths**. The academy captures one plan and runs it against two fresh, inert
   execution paths.
4. In **Without governance**, find `publish_external`: **1 attempt / 1 completion** means the inert
   training callable was entered and completed.
5. In **With Nornyx-derived controls**, find the same action: the recommended missing-approval
   case shows **0 attempts / 0 completions**, a real approval-required decision, and the named
   application enforcement point. The action was planned, but the protected callable was not
   entered.
6. Expand **Inspect ordered trace**, then **Inspect evidence and validation findings**. Read the
   producer, bindings, normalized events, missing fields, and limitation—not only the green/red
   status.
7. Read **What can this variant honestly claim?** The supported statement is deliberately scoped
   to this run and wrapped path; it is not a claim that every agent or publication route is
   governed.
8. Answer the knowledge check and choose **Check my answer**. Incorrect answers receive an
   explanation and may be retried. A passing answer plus the successful execution satisfies the
   module completion rule.
9. Choose **See saved progress** to confirm the execution, assessment attempt, score, and module
   status on **My dashboard**.

Nothing in this demonstration publishes externally. `publish_external` is an inert local training
callable, and every experiment starts with fresh state.

## How to read counters

Counters describe entry into and completion of the named business callable. They do not count
model tokens, proposals, decision evaluations, or evidence records.

| Counters | Meaning when the action was planned and evidence is sufficient |
|---|---|
| **0 attempts / 0 completions** | Prevented before the named callable was entered. Check the decision, enforcement point, and evidence before using the word “prevented.” |
| **1 attempt / 0 completions** | The callable was entered but did not complete. This is failure or a later stop, not pre-execution prevention. |
| **1 attempt / 1 completion** | The named inert callable completed. It does not mean a real external business action occurred. |
| **? / ? or incomplete evidence** | The academy cannot honestly conclude. Unknown is not zero. |

Nornyx decision evidence and application tool counters are related but separate. A denial from a
policy decision point is not prevention until an enforcement point applies it before the effect.

## Choose a learning route

Open **Learning paths** to compare seven routes for beginners, developers, agent engineers,
architects, governance/risk professionals, Nornyx practitioners, and complete-curriculum learners.
Each card shows its audience, prerequisites, estimated effort, concepts, progress, expected
outcomes, and completion criteria. Choose **View this path** to filter the curriculum. You can
change paths at any time; all paths share the same local learner record.

Open **Curriculum** to browse all 31 modules. Search by a topic such as “evidence,” filter by path
or difficulty, and open a module with **Start** or **Open**. Foundations `F0`–`F5` explain models,
prompts, context, tools, agent runtime patterns, and reliable AI engineering before the advanced
governance sequence.

## Complete a lesson

Every lesson page follows the same pattern:

1. Read **Why it matters**, the prerequisites, concepts, and **By the end, you can** outcomes.
2. Choose **Run this lesson**. The page waits for a structured service response; it never shows a
   terminal transcript or substitutes a fake result.
3. Inspect returned sections, structured tables, exact diagnostics, executable checks, and the
   stated safety boundary.
4. If the scenario says **unavailable**, read the reason. A required framework or capability that
   is absent cannot award executable credit.
5. Complete the knowledge check. Ordering questions are built by choosing each next step;
   policy-repair and bypass questions may allow more than one choice.
6. A module becomes **Complete** only when its execution requirement and its minimum assessment
   score have both passed. A failed assessment produces **Needs review**; merely opening the page
   changes nothing.

## Run controlled experiments

The **Five-minute demo** offers an expandable **Introduce a controlled failure** panel. You can
change prompt injection, the cooperative enforcement point, enforcement failure mode, approval
state, identity, observed revision, and deterministic/live planner selection. Change one field at
a time, run again, and compare the returned decision, counters, evidence, and claim.

For a larger comparison, open **Scenario workbench**. Presets include:

- expire the approval;
- change the observed contract revision;
- disable the enforcement point;
- make the enforcement surface fail open or fail closed;
- remove the injected instruction.

Choose **Run both variants** after selecting a preset. The result itself reports whether restoration
succeeded. Choose **Restore scenario** to return the controls to the recommended case. A failed
request or missing result is displayed as an error, never converted into an allow, deny, or pass.

## Explore and build a real Nornyx contract

### Contract explorer

Open **Contract explorer** and select Atlas or Ledger. Four synchronized views are available:

- **Visual** shows identities, capabilities, trust zones, gates, resources, and relationships;
- **Source** reveals the authoritative `.nyx` returned by the service;
- **Generated controls** shows the controls derived from the checked contract;
- **Diagnostics** shows exact codes, levels, semantic paths, and messages.

Generated controls are design-time outputs. Their presence does not prove that a runtime imported,
invoked, or made them unavoidable. A valid lock binds named bytes and revisions; it does not prove
correctness or runtime enforcement.

### Guided contract builder

Open **Guided builder**, select a base contract, and add semantic changes using the form. The
mutation queue can add, remove, or clear proposed changes before you choose **Apply and validate**.
The academy applies them only to an isolated copy, reparses and checks the actual contract with
Nornyx, and returns:

- whether the semantic document is valid;
- exact diagnostics;
- the authoritative returned source;
- generated-control previews;
- lock status.

The builder is not a second visual-only contract format. Canonical serialization may change YAML
layout or comments, so the result promises semantic paths and canonical content—not an exact
formatting round trip.

### Graph and diagnostics

Open **Agent & zone graph** to filter Atlas or Ledger by element type and inspect each node’s
declared fields. The graph proves what the contract declares, not which runtime path executed.

Open **Diagnostics** to introduce a controlled revision mismatch or remove an evidence field. The
viewer shows the exact returned code, path, validity, and lock state. Choose **Restore baseline** to
discard the isolated mutation.

## Simulate approval

Open **Approval simulator** and select a missing, valid human, expired, non-human, or wrong-revision
assertion. You may also supply an observed revision. Choose **Evaluate approval path**, then inspect
the decision, counters, trace, and claim cards.

The combined demonstration is a trust-zone crossing request carrying a bound approval assertion.
Validating an assertion does not authenticate the person who created it, permanently grant a
capability, or mutate the Authorizer. A generic capability request has no approval field.

## Inspect evidence and honest claims

Open **Evidence explorer** and choose **Run demo and load evidence** if no run is loaded. Switch
between **Without governance** and **With controls**. For each variant, inspect:

- producer and producer type;
- schema and validation status;
- ordered events and occurrence identifiers;
- decision and rule/gate data;
- contract revision and other bindings;
- findings and missing fields;
- attempt/completion counters;
- supported, unsupported, and indeterminate claims.

Evidence integrity means supplied records match their reported structure or bindings. It does not
by itself establish that all relevant events were supplied, that their assertions are true, or
that every alternative path was observed.

## Use the dashboard and learner record

Open **My dashboard** to see overall completion, the next current module, last activity, module
executions, assessment attempts, best scores, mastered concepts, review signals, and capstone
status. The record is local and requires no registration.

- **Export record** downloads a JSON completion report containing progress and assessment history.
  It is a learner record, not an identity credential, certification, or independent attestation.
- **Reset progress** opens a confirmation dialog. Reset removes all local executions, scores,
  concept signals, and capstone status. Export first if you want to keep a copy.

## Complete the capstone

Open **Capstone** after the practitioner sequence. The workspace provides a multi-identity
remediation brief, requirements, and guidance that can be reduced as confidence grows.

1. Select a framework surface, a controlled failure, and **Guided**, **Reduced scaffolding**, or
   **Independent review**.
2. Choose **Run capstone workflow**.
3. Inspect role separation, handoffs, typed decisions, denied and approved counters, execution
   timeline, evidence validation, and the business-call negative control.
4. Repeat with prompt injection, expired approval, artifact tamper, unauthorized delegation,
   replay, and bypass. A bypass is deliberately retained so a whole-system claim can be falsified.
5. Read the claim register, Tier 2 ceiling, and residual risk, then pass the capstone assessment at
   its higher threshold.

A framework name in a topology or configuration is not proof that its runtime executed. Trust the
returned runtime-executed field, named surface, evidence, and unavailable state.

## Settings and live-model mode

The deterministic local planner is the default and needs no key or network. Open **Settings** only
if an operator has enabled the optional live-model dependency and network access.

To opt in, enable **Live-model planner**, confirm the model, enter the API key, and choose **Save
live-model setting**. The key is held only in server-process memory, is never returned, logged,
stored in progress, or included in an export, and disappears when disabled or after restart.

Live mode may propose a different plan, so whole-run effects can differ. It cannot silently change
a Nornyx authorization result for an identical typed request. If live support is unavailable, the
academy reports the error; it never falls back to deterministic mode while labeling the result
live.

## Navigation and accessibility

All primary controls are keyboard reachable. Use the **Skip to main content** link to bypass
navigation. On a narrow screen, open the navigation menu and press **Escape** to close it. Statuses
use words and shapes as well as color; loading, success, warning, failure, and unknown remain
visually distinct. Dense graphs are easiest on a desktop or tablet, while their element directory
and lesson text remain readable on mobile.

Open **About & boundaries** whenever a claim feels too broad. It summarizes what Nornyx does and
does not do, the installed runtime and audited-source versions, the cooperative Tier 2 ceiling,
and the distinction between governance of an inert training target and protection of the academy
platform itself.

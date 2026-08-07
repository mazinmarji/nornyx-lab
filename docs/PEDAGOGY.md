# Pedagogical architecture

> The product owner used the academy and reported: *"I myself am not able to understand what
> the lab is trying to teach."*
>
> This document is the response. It is not a plan to simplify Nornyx. It is a plan to change
> **the order in which knowledge is introduced**.

## 1. Cognitive-load audit of the v1.0 journey

The v1.0 academy is technically correct and pedagogically inverted. Concrete findings, each
tied to the artifact that produces it.

### F1 — The homepage opens in specialist vocabulary

`HomePage.tsx` reaches the learner with `identity`, `capability`, `resource`, `zone`, `policy`,
`gate`, `approval`, `enforcement point`, `counters`, and `bound events` — **ten specialist terms
before a single problem has been shown**. The hero panel displays `atlas.publish_external` and
`untrusted.web → public.internet` as the *first concrete thing on the page*.

A learner cannot want a capability model before they have watched something go wrong.

### F2 — The demo teaches its notation before its story

`DemoPage.tsx` renders the counter key — `0 / 0`, `1 / 0`, `1 / 1`, `? / ?` — in the primer,
*above* the run button. These are the punchline of the entire curriculum, presented as a legend
to be memorised before the learner has any reason to care what a "completion" is.

### F3 — One button executes the whole lesson

"Run both paths" runs the ungoverned and governed variants simultaneously and renders every
panel at once. The contrast is the lesson, and it is delivered as a fait accompli. The learner
never forms an expectation, so the result cannot violate one — and a result that violates no
expectation teaches nothing.

### F4 — The result is a wall

`ScenarioResults.tsx` renders, in one pass: provenance, planner input, plan steps, comparison
table, then **two** variant panels each containing a flow diagram, three counter cards, a
decision-outcome grid, full decision cards, a trace timeline, an evidence panel and claim cards
— then an assurance summary. Roughly **thirty distinct information regions** with no ranking.
Nothing tells the learner which one is the point.

### F5 — "Run the structured scenario" is the visual centre of every lesson

In `LessonPage.tsx` the concept is a header; the execution panel is the prominent call to
action. The page is organised around *operating the machine*, not around *the idea*.

### F6 — Repository history is presented as the learning structure

The curriculum exposes `F0`–`F5` plus labs `00`–`24`. That is the order the repository was
built in, not the order a mind assembles the subject.

### F7 — No prediction, no plain-language result, no glossary, no mode

There is nowhere the learner is asked what they think will happen; no plain-language statement
of what occurred; no contextual definition of a term at the point of use; and no way to ask for
less detail. Every panel is at professional density permanently.

### Root cause

**The application teaches in the order the system executes, not the order a person learns.**
Execution artifacts are the primary surface, and the lesson is left as an inference the learner
is expected to perform unaided.

## 2. The pedagogical pattern

Every concept in the academy follows this ten-step sequence. It is a reusable structure, not a
one-off for the demo.

| # | Step | Obligation | Enforced by |
|---|---|---|---|
| 1 | **Understand** | Ordinary language, no unnecessary jargon | `teaching.json: question`, `plain_summary` |
| 2 | **See the problem** | A concrete situation creating the need | `story` |
| 3 | **Predict** | Ask before revealing; never scored | `prediction` |
| 4 | **Run** | One obvious action | single primary CTA |
| 5 | **Observe** | Most important consequence *first* | `headline` from the real run |
| 6 | **Explain** | Plain language cause and effect | derived `why` |
| 7 | **Name the concept** | Formal terminology, only now | `concept.formal_term` |
| 8 | **Connect to Nornyx** | What Nornyx declares/checks/decides/binds | derived `nornyx_role` |
| 9 | **Go deeper** | Contracts, codes, evidence, adapters | Explore mode |
| 10 | **Demonstrate understanding** | Small meaningful assessment | existing assessment engine |

**Product principle: teach first, execute second, inspect internals third.**

### The prediction rule

Prediction is **never** scored and never affects progress. Its only job is to make the learner
commit, so the observation can confirm or violate that commitment. A wrong prediction that gets
corrected teaches more than a right one, so the UI must not punish it.

## 3. Progressive disclosure: Guided and Explore

Two modes over **one engine**. This is the load-bearing constraint:

> Guided mode and Explore mode use the same scenario, the same API response and the same
> evidence. There is no simplified engine, no second data path, and no illustrative mock.
> Guided mode renders *less of the same truth*, ordered differently.

| | Guided (default) | Explore |
|---|---|---|
| Vocabulary | Plain first, formal as a subordinate label | Formal terms primary |
| Result | Headline consequence, then plain explanation | Full decision/trace/evidence stack |
| Controls | One or two relevant to this concept | All scenario options |
| `.nyx` source, locks, digests | Hidden | Shown |
| Diagnostic codes | Named in plain language | Exact codes |
| Counters | Explained before shown | Shown with formal meaning |

Mode is a learner preference, persisted with progress. Any learner may switch at any time; the
switch is always visible, because hiding the existence of depth would be its own dishonesty.

### What Guided mode may never hide

Guided mode reduces *density*, never *honesty*. These are present in both modes:

- the attempts/completions numbers themselves;
- the fact that the control is cooperative and in-process;
- what the run did **not** prove;
- the bypass — that other code paths can reach the same function.

Simplifying the vocabulary of a limitation is allowed. Removing the limitation is not.

## 4. Plain-language-first labels

Presentation layer only. **Canonical Nornyx field names in contracts, the SPI and API responses
are unchanged** — this is a relabelling of what the learner reads, not a rename of anything the
system computes with.

| Learner sees (primary) | Subordinate label | Canonical name (unchanged) |
|---|---|---|
| Governance decision | Policy Decision Point (PDP) | `decision` |
| Execution gate | Policy Enforcement Point (PEP) | `enforcement_point` |
| Version of the governed subject | `subject_revision` | `subject_revision` |
| Proof of delegated authority | authority assertion | `approval_assertion` |
| Who is acting | identity | `identity` |
| What it may do | capability | `capability` |
| Boundary being crossed | trust zone crossing | `source_zone` → `target_zone` |
| Record of what happened | evidence | `evidence` |

## 5. "What am I looking at?"

Every technical visualization carries a one-sentence explanation **immediately above it**,
answering why the panel exists before showing its contents. The learner is never expected to
infer a panel's purpose from its data.

## 6. Conceptual curriculum

Seven stages replace repository ordering as the learner's mental structure. Existing modules map
underneath; module identifiers remain for engineering, deep links and the migration matrix, but
they are **secondary** in presentation.

1. **Understand AI** — what a model does, prompts and context, why output can be wrong, structure and validation
2. **From AI to agents** — tools, what makes an agent, side effects, loops and retries, multiple agents
3. **Discover the governance problem** — wrong action vs wrong answer, identity, capability, boundaries, decisions, enforcement, approval
4. **Prove what happened** — attempts and completions, evidence, integrity, locks and drift, assurance limits, bypass
5. **Learn Nornyx** — contracts, generated controls, authoring, authorization, runtime evidence, CI
6. **Framework integration** — CrewAI, LangGraph, multi-agent governance
7. **Build it yourself** — capstone

### Progress is stated in concepts

> You understand: assistants vs agents · tools and side effects · why enforcement is required
> Next: identity and capability

Module counts remain available, but secondary.

## 7. The teach-me layer is derived, never authored

For every scenario result the academy produces six fields: **what happened, why, what Nornyx
contributed, what this proves, what this does not prove, remember.**

These are computed in `academy/explain.py` from the actual `ScenarioRun` — its decisions,
counters, evidence findings and claims. They are **not** authored strings selected by scenario
id.

This is a correctness requirement, not a style choice. Authored explanations would drift from
what the engine actually did, and the academy would then be teaching governance while itself
asserting an unverified claim about its own behaviour. If a run comes back with an unexpected
shape — inconsistent counters, a missing decision, evidence that failed validation — the derived
explanation must say so rather than narrate the outcome the lesson expected.

## 8. Beginner validation criterion

After the guided orientation and the reference demo, a learner with no prior Nornyx knowledge
must be able to answer, without external documentation:

1. What is the difference between an assistant and an agent?
2. Why does giving an agent tools create risk?
3. What is governance trying to control?
4. Why is saying "denied" different from preventing a tool call?
5. What do 0/0, 1/0 and 1/1 mean?
6. At a high level, what does Nornyx contribute?
7. What does Nornyx **not** do?
8. Why do we need evidence?

Each question is mapped to the screen that teaches it in
[`docs/BEGINNER_VALIDATION.md`](BEGINNER_VALIDATION.md), and the mapping is test-enforced.

## 9. Testing pedagogy

We test **structural invariants**, not prose quality. No test attempts to judge whether writing
is good.

- a prediction step exists and precedes the first execution;
- the plain-language result precedes the formal terminology;
- formal terms are introduced with a plain-language primary label;
- the result states both what was proved and what was not;
- advanced detail remains reachable;
- mode can be switched, and both modes render the same run;
- the assessment follows the teaching, never precedes it.

## 10. What this redesign does not change

Unchanged: the 25 lab mappings, deterministic planner, attempts/completions semantics, real
`.nyx` contracts, exact diagnostic codes, approvals, evidence, locks, adapter conformance,
CrewAI, LangGraph, capstone, the Tier-2 boundary, bypass teaching, CI and existing tests.

Depth is re-sequenced and progressively disclosed. None of it is removed.

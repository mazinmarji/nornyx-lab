# Beginner validation

The acceptance criterion for the pedagogical redesign is not the number of routes,
modules or tests. It is this:

> A learner with no prior knowledge of AI development, LLMs, agents, agentic frameworks,
> AI governance or Nornyx can answer the eight questions below after the guided
> orientation and the reference demonstration — **without reading external documentation.**

Each question is mapped to the screen that teaches it. If a mapping is empty, the
redesign is incomplete for that question.

## The eight questions

### 1. What is the difference between an assistant and an agent?

| Where | What it does |
|---|---|
| Orientation, ideas 1–3 | A model produces text and has no hands. A tool is your software. An agent chooses which tool to call, with no person in between. |
| Demo screen 1 | Atlas is shown with three abilities; the third is marked as leaving the building. |
| Lesson `F3`, `00` | The same plan runs with the tool disconnected and attached. |

Answerable after orientation alone.

### 2. Why does giving an agent tools create risk?

| Where | What it does |
|---|---|
| Orientation, idea 4 | The model can misunderstand, invent, or follow instructions hidden in a page it was only meant to read. |
| Demo screens 2–4 | The hidden line is shown on the page, then the ungoverned run records `1 / 1`. |

The demo makes it concrete: the risk is not that the model said something wrong,
it is that software then did it.

### 3. What is governance trying to control?

| Where | What it does |
|---|---|
| Orientation, idea 5 | Six plain questions asked before a sensitive action: who is acting, what are they trying to do, are they allowed, does a human need to approve, should this be blocked, what should we record. |
| Demo screen 5 | The learner picks the point in the chain where a check would help. |

Governance is introduced as controlling **actions**, never text.

### 4. Why is saying "denied" different from preventing a tool call?

| Where | What it does |
|---|---|
| Demo screen 5 | The gap between agent and tool is identified by the learner, then named: execution gate / PEP. |
| Demo screen 8 | Four candidate proofs are compared; "the AI said I refused" and "the application displayed blocked" are shown to be weaker than the observed ledger. |
| Lesson `01`, `03` | `03` is the dedicated lesson: a DENY decision with the enforcement point removed. |

### 5. What do 0/0, 1/0 and 1/1 mean?

| Where | What it does |
|---|---|
| Demo screen 4 | The counter is explained **before** it is shown: "these two numbers tell us whether software actually reached and completed the sensitive function." Ungoverned reads `1 / 1 Executed`. |
| Demo screen 6 | Governed reads `0 / 0 Prevented before execution`. |
| Lesson `10` | All three readings, including `1 / 0` — started and did not finish. |
| Glossary | `attempt`, `completion`. |

Note the ordering: in v1.0 this legend appeared above the run button, before the
learner had any reason to care. It now appears as the answer to something watched.

### 6. At a high level, what does Nornyx contribute?

| Where | What it does |
|---|---|
| Orientation, closing | "A structured way to write down those rules, check that they make sense, and produce the controls and the records used around the agent system." |
| Demo screen 7 | Layered comparison: without Nornyx the rules are scattered; with it, contract → checked definition → derived controls → enforcement surface → tool → evidence. |
| Every run | The derived `What Nornyx contributed` names the actual contract and decision code from that run. |

### 7. What does Nornyx **not** do?

| Where | What it does |
|---|---|
| Orientation, Nornyx position | "It does not run your agent and it does not replace your framework." |
| Demo screen 7 | Stated as a boundary directly under the diagram. |
| Demo screen 9 | Four things the run did not prove. |
| Home page | "What this academy will not claim." |

### 8. Why do we need evidence?

| Where | What it does |
|---|---|
| Demo screen 8 | The question is asked as "how do we know?", with four competing answers. |
| Demo screen 9 | Tier 2 named only after the concrete limitations are understood. |
| Lesson `10`, `11`, `12` | Evidence is not logging; integrity is not truth; producer independence bounds the claim. |

## What is deliberately not claimed

A learner finishing the orientation and demo will **not** be able to write a `.nyx`
contract, choose an enforcement architecture, or run a conformance suite. Those are
stages 5 and 6. The criterion above is about comprehension of the problem, which is
what the product owner reported was missing.

## How this is enforced

Structural invariants live in `tests/academy/test_pedagogy.py` and
`frontend/e2e/guided-journey.spec.ts`:

- the orientation contains no specialist vocabulary (test asserts absence of PDP,
  PEP, assurance tier, subject revision, trust zone, occurrence identity);
- the demo asks for a prediction before its first run;
- limits are stated after the proof, never before;
- every lesson has a plain title, a one-sentence learning statement, a prediction,
  a plain concept name paired with its formal term, and a takeaway;
- the assessment never precedes the run.

No test tries to judge whether the prose is good. That remains a human question, and
the honest answer to it is the product owner's to give.

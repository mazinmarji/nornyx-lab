# Academy design principles

This document is an **acceptance contract**, not advisory guidance. Any feature
that reports mastery, readiness, advanced standing, certification-like status,
or any similar claim about a learner must be reviewed against it before merge.

## The evidence chain

> **visible → decided → authored → accepted as evidence → competence demonstrated**

Each arrow is a transition that must be **proven**, never inferred from the
state before it. Showing a learner a control does not mean they decided it;
a decision on one field does not make a section authored; an authored design
is not evidence until it survives validation; and accepted evidence
substantiates only the competence it actually tests.

The product-level form:

> **Completion is activity evidence. Competence requires demonstrated
> reasoning evidence.**

Finishing instructional material, running a scaffolded walkthrough, or opening
every panel is activity. None of it may be reported as understanding, mastery,
or independent competence.

## Implementation rules

1. **Undecided by default.** A control whose value will be recorded as a
   learner decision starts unset. Submission stays blocked until every
   applicable decision is made. A preselected value the learner never touched
   is academy authorship and must never be reported otherwise.
2. **Omitted ≠ explicit null.** An absent field means "accept the academy
   default" and is legitimate only where the scaffolding level permits
   defaults. An explicit null is either a real decision (where the domain
   allows it — record it as the learner's) or an error (where it does not —
   reject it). Never silently replace either with a default.
3. **Field-complete ≠ non-empty.** Where a level claims the learner authored a
   section, the section must contain every decision it carries. A partial
   section silently completed with defaults is manufactured authorship.
4. **The backend re-verifies what the UI claims.** API completeness is not
   learner authorship; client-side gating is presentation, not proof. Every
   claim the browser submits must be independently checkable and checked.
5. **Adversarial tests are part of the feature.** Every standing-reporting
   feature ships with tests that actively try to earn standing through
   defaults, partial input, preselection, replay or stale persisted state,
   empty containers, and any other shortcut — together with a fully explicit
   positive control. Proving only that bad paths fail is not enough; the
   acceptance-test pattern is:

   > shortcut attempts fail → explicit valid path succeeds → standing follows
   > only from that valid evidence.

## Reference implementation

The capstone advanced-standing path is the current reference implementation
for authorship, field-completeness, transfer, and request-capture
enforcement: the gates in `src/nornyx_lab/academy/capstone.py`, the derived
concept-evidence model in `src/nornyx_lab/academy/progress.py`, and the
request-capture regressions in `frontend/src/pages/CapstonePage.test.tsx`.

Stale-evidence invalidation, previously listed here as outstanding, is now
implemented in `src/nornyx_lab/academy/competence.py` and enforced by the
learner record. Evidence acceptance means:

> evidence payload
> + the semantic revision it was earned under
> + the current compatibility rule
> → admissible evidence

The principle itself is not coupled to the capstone and applies to every
feature that reports learner standing.

## Evidence expiry

Learner evidence records the competence semantics it was earned under, and is
re-evaluated against the current contract on every read.

**What defines a revision.** `content/competence.json` declares a revision per
evidence *family* — `assessment` (the learner-visible stimulus: prompt,
context, and the labelled options an answer id points at, plus which concepts
the item tests, what counts as a correct answer, and the passing threshold) and
`capstone` (each scenario's
consequential boundary and required workflow actions, the declared identities
and zones, and the field-completeness rules that define authorship). Families
are separate so editing one module's assessment does not invalidate unrelated
capstone authorship. A package or Nornyx version is **not** a competence
binding: `nornyx-lab` stays at one version across curriculum edits, so a
release number cannot answer whether the meaning of evidence changed.

**How compatibility is determined.** Only by explicit declaration. A prior
revision counts if and only if the family lists it in `compatible_with`.
Compatibility is never inferred from ordering, recency, timestamps, package
versions, or name similarity, and a family's `compatible_with` may not contain
its own revision.

**How drift is caught.** Each family also declares a digest of the authored
semantics its revision stands for; `tests/academy/test_competence_contract.py`
recomputes that digest and fails when the two disagree. A semantic edit that
arrives without a revision decision therefore fails CI rather than silently
preserving standing.

The assessment digest deliberately covers the whole stimulus, not just the
answer key. `correct` stores option *ids*, and an id means nothing by itself:
relabelling the option it points at, or negating the prompt, inverts what the
learner had to demonstrate while every id stays identical. Only material shown
*after* scoring — explanations — is excluded, because it cannot change what was
demonstrated. A genuinely wording-only improvement is therefore handled by a
new revision that explicitly declares the prior one compatible: a decision on
the record, which is safer than a digest guessing whether prose changed
meaning.

The digest covers authored data. Changes to the rule
*code* — the authorship gates, the advanced-standing composition — are a
maintainer obligation: **bump the family revision in the same change**, and add
the prior revision to `compatible_with` only if existing evidence genuinely
still holds. Overwriting a digest to make the gate green, while leaving the
revision untouched, re-creates the exact defect this section exists to prevent.

**Legacy and unbound evidence.** Rows written before the binding existed carry
no revision. That is recorded honestly as unbound and **never backfilled** — the
semantics those rows were earned under are genuinely unknown, and inventing one
would manufacture the admissibility the binding exists to establish. Unbound
evidence does not support present-tense competence.

**When re-demonstration is required.** Whenever a required evidence item is
incompatible or unbound. The learner is told which — `AdvancedStanding.
requires_redemonstration` and `concepts_requiring_redemonstration` distinguish
*never demonstrated* from *demonstrated under an older definition*, so the
product says "show this again", never the false "you never did this".

**Why historical rows are retained.** Deleting them would destroy the true
record that the work happened, and truthful history is not the same thing as
current admissibility. The two are kept apart: **a record exists** is a fact
about the past; **a record is admissible competence evidence** is a claim about
the present, and only the second expires.

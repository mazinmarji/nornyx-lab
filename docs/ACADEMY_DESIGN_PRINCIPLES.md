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

It is **not yet a complete reference for every rule in this contract**:
persisted capstone and assessment evidence is not currently revalidated
against a versioned competence contract when Academy semantics change, so
historical rows can continue to support advanced standing after the semantics
that earned them have moved. Stale-evidence invalidation therefore remains a
separate implementation requirement. When it lands, evidence acceptance
should mean: evidence payload + the assessment/capstone semantic revision it
was earned under + a current compatibility/revalidation rule — with
historical evidence either remaining valid because its binding is still
compatible, being explicitly revalidated, or degrading to "evidence requires
re-demonstration"; never silently retaining standing.

The principle itself is not coupled to the capstone and applies to every
feature that reports learner standing.

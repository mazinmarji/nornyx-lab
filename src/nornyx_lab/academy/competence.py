"""The competence contract: what learner evidence *means*, and when it expires.

Learner evidence is only as good as the semantics it was earned under. If an
assessment is redefined, or the capstone's design rules change, a row recorded
before that change no longer demonstrates what it claimed to demonstrate. This
module supplies the missing half of the evidence model:

    evidence payload
    + the semantic revision it was earned under
    + a current compatibility rule
    -> admissible evidence

Every stored evidence row therefore resolves to exactly one honest outcome —
``CURRENT``, ``COMPATIBLE``, ``INCOMPATIBLE`` or ``UNBOUND`` — and only the
first two may support a present-tense competence claim. There is deliberately
no fifth state in which a row counts merely because it still exists.

Two things this module is careful *not* to do:

* It does not reuse the package or Nornyx version as a competence binding.
  ``nornyx-lab`` sits at 2.0.0 across curriculum edits, so a release number
  cannot answer "did the meaning of this evidence change?".
* It does not infer compatibility. A prior revision is admissible only when the
  contract names it, never because it sorts earlier, was recorded later, or
  looks similar.

Drift is handled the way this repository teaches it: the contract *declares* a
semantic digest, the digest is *recomputed* from the authored inputs, and a
test fails when the two disagree. That gate covers the authored data
(assessment declarations, capstone scenario semantics). Changes to the rule
*code* — the authorship gates, the advanced-standing composition — are a
maintainer decision and require an explicit revision bump, which
``docs/ACADEMY_DESIGN_PRINCIPLES.md`` states as an obligation rather than
pretending the digest catches it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from typing import Any


class EvidenceFamily(str, Enum):
    """A body of evidence governed by one set of semantics.

    Families are separate because their meanings move independently: editing a
    module's assessment must not invalidate a learner's capstone authorship,
    and rewriting the capstone design rules must not wipe unrelated concept
    evidence. Each evidence row is judged against the family that defines it.
    """

    ASSESSMENT = "assessment"
    CAPSTONE = "capstone"


class Admissibility(str, Enum):
    CURRENT = "current"
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNBOUND = "unbound"

    @property
    def admissible(self) -> bool:
        return self in {Admissibility.CURRENT, Admissibility.COMPATIBLE}


@dataclass(frozen=True)
class FamilyRule:
    """The current revision of one family, and the priors it still accepts."""

    revision: str
    compatible_with: tuple[str, ...] = ()
    semantic_digest: str = ""

    def admits(self, revision: str | None) -> Admissibility:
        if not revision:
            return Admissibility.UNBOUND
        if revision == self.revision:
            return Admissibility.CURRENT
        if revision in self.compatible_with:
            return Admissibility.COMPATIBLE
        return Admissibility.INCOMPATIBLE


class CompetenceContract:
    """Loaded declaration of what each evidence family currently means."""

    def __init__(self, families: Mapping[str, FamilyRule]) -> None:
        for name, rule in families.items():
            # Listing the current revision as a compatible prior is a category
            # error: compatibility describes superseded revisions. Rejected at
            # construction so an in-memory contract cannot express it either.
            if rule.revision in rule.compatible_with:
                raise ValueError(
                    f"{name} lists its own revision as a compatible prior; "
                    "compatibility describes superseded revisions only"
                )
        self._families = dict(families)

    @classmethod
    def load(cls) -> CompetenceContract:
        raw = json.loads(
            files("nornyx_lab.academy.content")
            .joinpath("competence.json")
            .read_text(encoding="utf-8")
        )
        families = {
            name: FamilyRule(
                revision=str(item["revision"]),
                compatible_with=tuple(item.get("compatible_with", ())),
                semantic_digest=str(item.get("semantic_digest", "")),
            )
            for name, item in raw["families"].items()
        }
        missing = {family.value for family in EvidenceFamily} - set(families)
        if missing:
            raise ValueError(f"competence contract is missing families: {sorted(missing)}")
        return cls(families)

    def _rule(self, family: EvidenceFamily | str) -> FamilyRule | None:
        key = family.value if isinstance(family, EvidenceFamily) else str(family)
        return self._families.get(key)

    def revision(self, family: EvidenceFamily | str) -> str:
        rule = self._rule(family)
        if rule is None:
            # An unknown family has no declared meaning, so nothing recorded
            # under it could be evaluated later. Refuse to stamp it.
            raise KeyError(f"no competence revision declared for family {family!r}")
        return rule.revision

    def admits(self, family: EvidenceFamily | str, revision: str | None) -> Admissibility:
        """Classify one stored revision. Unknown families fail closed."""

        rule = self._rule(family)
        if rule is None:
            return Admissibility.INCOMPATIBLE
        return rule.admits(revision)

    def declared_digest(self, family: EvidenceFamily | str) -> str:
        rule = self._rule(family)
        return rule.semantic_digest if rule else ""

    def families(self) -> tuple[str, ...]:
        return tuple(sorted(self._families))


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def compute_assessment_digest(definitions: Iterable[Any]) -> str:
    """Digest everything that decides what passing an assessment proves.

    ``correct`` holds option *ids*, and an id means nothing on its own: what
    the learner had to demonstrate is fixed by the prompt, the context, and the
    label attached to that id. Relabelling option ``a`` from "Require human
    approval" to "Allow without human approval", or negating a prompt, inverts
    the item's meaning while every id stays put — so the stimulus is part of
    the digest. Options are canonicalised by id, so reordering them (pure
    presentation) does not raise false drift.

    Excluded: ``explanation`` and ``incorrect_explanations``. Those are shown
    after scoring and cannot change what the learner had to demonstrate.

    A genuinely wording-only improvement is not blocked by this — it is handled
    the safe way, with a new revision that explicitly declares the prior one
    compatible. That is a deliberate decision on the record, which is strictly
    better than a digest trying to guess whether prose changed meaning.
    """

    rows = [
        {
            "id": item.id,
            "module_id": item.module_id,
            "kind": item.kind.value if hasattr(item.kind, "value") else str(item.kind),
            "concepts": sorted(item.concepts),
            "prompt": item.prompt,
            "context": item.context,
            "options": sorted(
                ({"id": option.id, "label": option.label} for option in item.options),
                key=lambda option: option["id"],
            ),
            "correct": list(item.correct),
            "minimum_score": item.minimum_score,
        }
        for item in definitions
    ]
    rows.sort(key=lambda row: row["id"])
    return _digest(rows)


def compute_capstone_digest(
    scenarios: Iterable[Any],
    *,
    declared_identities: Iterable[str],
    declared_zones: Iterable[str],
    required_sections: Mapping[str, Iterable[str]],
) -> str:
    """Digest the capstone semantics that decide what a completed run proves.

    Included: each scenario's consequential boundary and required workflow
    actions with their expected capabilities, the declared identities and zones
    a design may draw on, and the per-section field-completeness requirements
    that define authorship. Together these fix what "a valid learner-authored
    design" means; changing any of them changes what an eligible run evidences.
    """

    payload = {
        "scenarios": sorted(
            (
                {
                    "id": scenario.id,
                    "consequential_action": scenario.consequential_action,
                    "action_capabilities": dict(sorted(scenario.action_capabilities.items())),
                    "uses_zone_crossing": scenario.uses_zone_crossing,
                }
                for scenario in scenarios
            ),
            key=lambda row: row["id"],
        ),
        "declared_identities": sorted(declared_identities),
        "declared_zones": sorted(declared_zones),
        "required_sections": {
            key: sorted(value) for key, value in sorted(required_sections.items())
        },
    }
    return _digest(payload)


__all__ = [
    "Admissibility",
    "CompetenceContract",
    "EvidenceFamily",
    "FamilyRule",
    "compute_assessment_digest",
    "compute_capstone_digest",
]

"""Teaching structures: orientation, glossary, conceptual stages, lesson scaffolds.

This module owns the *order* knowledge is introduced in. It deliberately holds no
governance logic: nothing here decides, enforces, or interprets a run. Statements
about what a particular run did are derived in `explain.py` from that run.

The one rule worth stating: `LessonTeaching.nornyx_role` is authored teaching
material describing what Nornyx is responsible for in a topic. It must never be
phrased as a claim about what a specific execution produced, because nothing
verifies authored text.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .schemas import (
    CurriculumStage,
    Glossary,
    GlossaryTerm,
    LessonTeaching,
    ModuleStatus,
    NamedConcept,
    Orientation,
    Prediction,
    PredictionOption,
    RemediationGuidance,
    RemediationRegistry,
    StageEntry,
    StageMap,
    StageStep,
)

UNKNOWN_CODE_NOTICE = "No remediation guidance is registered for this code."


def _load(name: str) -> Any:
    return json.loads(
        files("nornyx_lab.academy.content").joinpath(name).read_text(encoding="utf-8")
    )


class PedagogyRepository:
    """Loads the authored teaching layer and binds it to live progress."""

    def __init__(self) -> None:
        self._orientation = _load("orientation.json")
        self._glossary = _load("glossary.json")
        self._stages = _load("stages.json")
        self._teaching = _load("teaching.json")
        self._demo_story = _load("demo_story.json")
        self._remediation = _load("remediation.json")
        self._terms: dict[str, GlossaryTerm] = {
            item["id"]: GlossaryTerm(**item) for item in self._glossary["terms"]
        }

    # ------------------------------------------------------------- orientation
    def orientation(self) -> Orientation:
        return Orientation(**self._orientation)

    def demo_story(self) -> dict[str, Any]:
        """Returned as-is: the browser owns how these screens are laid out."""
        return dict(self._demo_story)

    # ---------------------------------------------------------------- glossary
    def glossary(self) -> Glossary:
        return Glossary(version=self._glossary["version"], terms=tuple(self._terms.values()))

    # ------------------------------------------------------------- remediation
    def remediation(self) -> RemediationRegistry:
        """Authored guidance per diagnostic code.

        Served as its own registry rather than attached to each diagnostic, so a
        hint is never mistaken for part of the runtime decision it accompanies,
        and so new codes are purely additive.
        """
        return RemediationRegistry(
            version=self._remediation["version"],
            provenance_label=self._remediation["provenance_label"],
            unknown_code_notice=UNKNOWN_CODE_NOTICE,
            entries=tuple(
                RemediationGuidance(code=code, **entry)
                for code, entry in sorted(self._remediation["entries"].items())
            ),
        )

    def remediation_for(self, code: str) -> RemediationGuidance | None:
        """None for an unregistered code; the caller renders the notice.

        Guessing guidance from the shape of a code's name would be inventing
        behaviour, which is the failure mode this curriculum exists to teach
        against.
        """
        entry = self._remediation["entries"].get(code)
        return RemediationGuidance(code=code, **entry) if entry else None

    def terms_for(self, ids: tuple[str, ...]) -> tuple[GlossaryTerm, ...]:
        """Unknown ids are dropped rather than raising.

        A lesson referencing a term that no longer exists is a content bug worth
        failing in tests, not worth breaking a learner's page over.
        """
        return tuple(self._terms[item] for item in ids if item in self._terms)

    # ------------------------------------------------------------------ stages
    def stages(self, module_status: dict[str, ModuleStatus] | None = None) -> StageMap:
        status = module_status or {}

        def step_complete(step: dict[str, Any]) -> bool:
            # A conceptual step counts as understood only when every module that
            # teaches it is complete. Partial credit would overstate progress.
            return bool(step["module_ids"]) and all(
                status.get(module_id) is ModuleStatus.COMPLETE for module_id in step["module_ids"]
            )

        stages: list[CurriculumStage] = []
        understood: list[str] = []
        upcoming: list[str] = []
        for stage in self._stages["stages"]:
            steps = tuple(StageStep(**step) for step in stage["steps"])
            done = sum(step_complete(step) for step in stage["steps"])
            for step in stage["steps"]:
                (understood if step_complete(step) else upcoming).append(step["name"])
            stages.append(
                CurriculumStage(
                    id=stage["id"],
                    number=stage["number"],
                    name=stage["name"],
                    question=stage["question"],
                    plain=stage["plain"],
                    steps=steps,
                    completed_steps=done,
                    total_steps=len(steps),
                )
            )
        return StageMap(
            version=self._stages["version"],
            entry=StageEntry(**self._stages["entry"]),
            stages=tuple(stages),
            understood_concepts=tuple(understood),
            next_concepts=tuple(upcoming[:3]),
        )

    # ---------------------------------------------------------------- lessons
    def teaching(self, module_id: str) -> LessonTeaching:
        try:
            item = self._teaching["modules"][module_id]
        except KeyError as exc:
            raise KeyError(f"no lesson scaffold authored for module {module_id!r}") from exc
        prediction = item["prediction"]
        return LessonTeaching(
            module_id=module_id,
            plain_title=item["plain_title"],
            learn=item["learn"],
            question=item["question"],
            why_you_care=item["why_you_care"],
            story=item["story"],
            prediction=Prediction(
                prompt=prediction["prompt"],
                options=tuple(
                    PredictionOption(label=label)
                    if isinstance(label, str)
                    else PredictionOption(**label)
                    for label in prediction["options"]
                ),
            ),
            concept=NamedConcept(**item["concept"]),
            nornyx_role=item["nornyx_role"],
            takeaway=item["takeaway"],
            glossary=self.terms_for(tuple(item.get("glossary", ()))),
        )

    def authored_module_ids(self) -> frozenset[str]:
        return frozenset(self._teaching["modules"])

    def referenced_term_ids(self) -> frozenset[str]:
        return frozenset(
            term for item in self._teaching["modules"].values() for term in item.get("glossary", ())
        )

    def known_term_ids(self) -> frozenset[str]:
        return frozenset(self._terms)

    def staged_module_ids(self) -> frozenset[str]:
        return frozenset(
            module_id
            for stage in self._stages["stages"]
            for step in stage["steps"]
            for module_id in step["module_ids"]
        ) | frozenset(self._stages["entry"]["module_ids"])

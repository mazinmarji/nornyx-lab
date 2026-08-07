"""Structured curriculum and audience-path repository."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

from nornyx_lab.engine import all_labs

from .schemas import (
    CompletionRule,
    ConceptRef,
    CurriculumCatalog,
    CurriculumModule,
    Difficulty,
    LearningPath,
    ModuleKind,
    ModuleProgress,
    ModuleStatus,
)

CONCEPT_SUMMARIES: dict[str, str] = {
    "assistant": "A model-backed system that produces information but has no effectful tool authority by itself.",
    "agent": "A planner or model connected to tools and an execution loop that can cause side effects.",
    "large language model": "A probabilistic model that generates token sequences from learned patterns and supplied context.",
    "prompt": "Instructions and other text supplied to a model for one generation.",
    "context": "The bounded information made available to a model for a request.",
    "tool": "An application-owned callable exposed to an assistant or agent.",
    "side effect": "An observable change outside model text, such as publishing, refunding, or modifying data.",
    "policy decision point": "The component that evaluates a request and returns a policy decision.",
    "policy enforcement point": "The component that applies a decision before a protected effect path.",
    "attempt": "Entry into the protected business callable; it is distinct from a proposal or request.",
    "completion": "Successful completion of the inert business effect after tool entry.",
    "evidence": "Structured records used to support a bounded governance claim.",
    "assurance boundary": "The exact surface, mechanism, producer, adversary, and limitation to which a claim applies.",
    "prompt injection": "Untrusted text attempting to act as authority rather than information.",
    "trust zone": "A declared governance boundary with memberships, transitions, sharing rules, and gates.",
    "capability": "A declared bounded action class; declaration does not itself grant it to an identity.",
    "approval": "A bounded assertion tied to actor type, role, action, evidence, revision, and time.",
    "lock": "A content and revision binding for a declared design-time artifact set.",
    "adapter": "A framework-specific cooperative enforcement layer that maps a runtime surface to the Nornyx SPI.",
    "coverage": "An inventory of concrete effect paths classified by their actual enforcement status.",
}


def _load_json(name: str) -> Any:
    return json.loads(
        files("nornyx_lab.academy.content").joinpath(name).read_text(encoding="utf-8")
    )


def _difficulty(value: str) -> Difficulty:
    try:
        return Difficulty(value.lower())
    except ValueError:
        return Difficulty.INTERMEDIATE


def _concept_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "concept"


class CurriculumRepository:
    """Loads versioned authored enrichment and verified legacy metadata."""

    def __init__(self) -> None:
        authored = _load_json("modules.json")
        self.version = str(authored["version"])
        self._foundation_data = tuple(authored["foundations"])
        self._lab_data = dict(authored["labs"])
        self._path_data = tuple(_load_json("paths.json"))

    def modules(
        self, progress: dict[str, ModuleProgress] | None = None
    ) -> tuple[CurriculumModule, ...]:
        progress = progress or {}
        modules: list[CurriculumModule] = []

        for item in self._foundation_data:
            module_progress = progress.get(item["id"])
            modules.append(
                CurriculumModule(
                    id=item["id"],
                    kind=ModuleKind.FOUNDATION,
                    title=item["title"],
                    eyebrow=item["eyebrow"],
                    summary=item["summary"],
                    why_it_matters=item["why_it_matters"],
                    difficulty=_difficulty(item["difficulty"]),
                    minutes=int(item["minutes"]),
                    prerequisites=tuple(item["prerequisites"]),
                    concepts=tuple(item["concepts"]),
                    outcomes=tuple(item["outcomes"]),
                    interaction=item["interaction"],
                    scenario_id=item["scenario_id"],
                    completion=CompletionRule(
                        assessment_id=item["assessment_id"], requires_execution=True
                    ),
                    status=(
                        module_progress.status if module_progress else ModuleStatus.NOT_STARTED
                    ),
                    score=(module_progress.best_score if module_progress else None),
                )
            )

        seen_labs: set[str] = set()
        for meta in all_labs():
            seen_labs.add(meta.id)
            try:
                item = self._lab_data[meta.id]
            except KeyError as exc:
                raise ValueError(f"academy enrichment missing legacy lab {meta.id}") from exc
            module_progress = progress.get(meta.id)
            modules.append(
                CurriculumModule(
                    id=meta.id,
                    legacy_lab_id=meta.id,
                    kind=ModuleKind.CAPSTONE if meta.id == "24" else ModuleKind.LAB,
                    title=meta.title,
                    eyebrow=meta.part,
                    summary=item["summary"],
                    why_it_matters=item["why_it_matters"],
                    difficulty=_difficulty(meta.difficulty),
                    minutes=meta.minutes,
                    prerequisites=meta.requires,
                    concepts=meta.concepts,
                    outcomes=meta.objectives,
                    interaction=item["interaction"],
                    scenario_id=item["scenario_id"],
                    completion=CompletionRule(
                        assessment_id=item["assessment_id"],
                        requires_execution=True,
                        minimum_score=0.85 if meta.id == "24" else 0.8,
                    ),
                    migration_classification=item["migration_classification"],
                    status=(
                        module_progress.status if module_progress else ModuleStatus.NOT_STARTED
                    ),
                    score=(module_progress.best_score if module_progress else None),
                )
            )

        extras = sorted(set(self._lab_data) - seen_labs)
        if extras:
            raise ValueError(f"academy enrichment references unknown labs: {extras}")
        return tuple(modules)

    def module(
        self, module_id: str, progress: dict[str, ModuleProgress] | None = None
    ) -> CurriculumModule:
        for module in self.modules(progress):
            if module.id == module_id:
                return module
        raise KeyError(f"unknown curriculum module {module_id!r}")

    def paths(
        self, modules: tuple[CurriculumModule, ...] | None = None
    ) -> tuple[LearningPath, ...]:
        modules = modules or self.modules()
        by_id = {module.id: module for module in modules}
        paths: list[LearningPath] = []
        for item in self._path_data:
            missing = [module_id for module_id in item["module_ids"] if module_id not in by_id]
            if missing:
                raise ValueError(f"path {item['id']} references unknown modules: {missing}")
            selected = tuple(by_id[module_id] for module_id in item["module_ids"])
            concepts = sorted({concept for module in selected for concept in module.concepts})
            completed = sum(module.status == ModuleStatus.COMPLETE for module in selected)
            paths.append(
                LearningPath(
                    id=item["id"],
                    title=item["title"],
                    audience=item["audience"],
                    summary=item["summary"],
                    prerequisites=tuple(item["prerequisites"]),
                    estimated_minutes=sum(module.minutes for module in selected),
                    concepts=tuple(concepts),
                    module_ids=tuple(item["module_ids"]),
                    outcomes=tuple(item["outcomes"]),
                    completion_criteria=item["completion_criteria"],
                    completed_modules=completed,
                    total_modules=len(selected),
                )
            )
        return tuple(paths)

    def concepts(
        self, modules: tuple[CurriculumModule, ...] | None = None
    ) -> tuple[ConceptRef, ...]:
        modules = modules or self.modules()
        names = sorted({concept for module in modules for concept in module.concepts})
        return tuple(
            ConceptRef(
                id=_concept_id(name),
                name=name,
                summary=CONCEPT_SUMMARIES.get(
                    name.lower(),
                    f"A curriculum concept introduced and exercised in the academy: {name}.",
                ),
            )
            for name in names
        )

    def catalog(self, progress: dict[str, ModuleProgress] | None = None) -> CurriculumCatalog:
        modules = self.modules(progress)
        return CurriculumCatalog(
            version=self.version,
            modules=modules,
            paths=self.paths(modules),
            concepts=self.concepts(modules),
        )

    def migration_rows(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "legacy_lab_id": module.id,
                "title": module.title,
                "classification": module.migration_classification or "new",
                "gui_interaction": module.interaction,
                "scenario_id": module.scenario_id or "",
                "assessment_id": module.completion.assessment_id,
            }
            for module in self.modules()
            if module.legacy_lab_id is not None
        )

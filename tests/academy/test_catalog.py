from __future__ import annotations

from nornyx_lab.academy.catalog import CurriculumRepository
from nornyx_lab.academy.schemas import ModuleProgress, ModuleStatus


def test_catalog_covers_foundations_and_every_legacy_lab() -> None:
    repository = CurriculumRepository()
    catalog = repository.catalog()

    assert len(catalog.modules) == 31
    assert [module.id for module in catalog.modules[:6]] == [
        "F0",
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    ]
    assert {module.legacy_lab_id for module in catalog.modules if module.legacy_lab_id} == {
        f"{index:02d}" for index in range(25)
    }
    assert len(catalog.paths) == 7
    assert len(catalog.concepts) >= 150
    assert catalog.modules[0].scenario_id == "atlas-five-minute"
    assert catalog.modules[0].completion.assessment_id == "assessment.F0"


def test_every_path_references_real_modules_and_exposes_outcomes() -> None:
    catalog = CurriculumRepository().catalog()
    module_ids = {module.id for module in catalog.modules}

    for path in catalog.paths:
        assert path.module_ids
        assert set(path.module_ids) <= module_ids
        assert path.total_modules == len(path.module_ids)
        assert path.estimated_minutes > 0
        assert path.outcomes
        assert path.completion_criteria


def test_catalog_projects_typed_progress_into_modules_and_paths() -> None:
    repository = CurriculumRepository()
    progress = {
        "F0": ModuleProgress(
            module_id="F0",
            status=ModuleStatus.COMPLETE,
            executions=1,
            assessment_attempts=1,
            best_score=1.0,
        )
    }

    catalog = repository.catalog(progress)

    assert catalog.modules[0].status is ModuleStatus.COMPLETE
    assert catalog.modules[0].score == 1.0
    assert any(path.completed_modules == 1 for path in catalog.paths if "F0" in path.module_ids)


def test_migration_map_has_one_browser_interaction_for_each_legacy_lab() -> None:
    rows = CurriculumRepository().migration_rows()

    assert len(rows) == 25
    assert {row["legacy_lab_id"] for row in rows} == {f"{index:02d}" for index in range(25)}
    assert all(row["classification"] for row in rows)
    assert all(row["gui_interaction"] for row in rows)
    assert all("terminal" not in row["gui_interaction"].lower() for row in rows)
    assert all(row["assessment_id"].startswith("assessment.") for row in rows)

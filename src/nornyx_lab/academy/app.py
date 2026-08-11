"""FastAPI composition root for the GUI-first Nornyx Academy."""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

# CrewAI initializes tracing while it is imported. These process controls must
# be present before any adapter or legacy lab can import the framework.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_TESTING", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .advanced import AdvancedInputError, run_advanced_module
from .assessments import AssessmentService
from .catalog import CurriculumRepository
from .contracts import ContractWorkbenchError, get_contract, list_contracts, validate_workbench
from .feedback import (
    FeedbackConfiguration,
    FeedbackService,
    SQLiteFeedbackRepository,
)
from .feedback_client import FeedbackTransport
from .foundations import FoundationInputError, run_foundation
from .pedagogy import PedagogyRepository
from .progress import SQLiteLearnerRecordRepository
from .scenarios import ScenarioUnavailable, run_atlas_demo
from .schemas import (
    API_VERSION,
    AssessmentResult,
    AssessmentSubmission,
    CapstoneDefinition,
    CapstoneRunRequest,
    ContractDetail,
    ContractSummary,
    ContractValidation,
    ContractWorkbenchRequest,
    CourseFeedbackRequest,
    CurriculumCatalog,
    CurriculumModule,
    Dashboard,
    DemoOptions,
    DestinationVisibility,
    FeedbackConsentRequest,
    FeedbackDeletionResponse,
    FeedbackStatus,
    FeedbackSubmissionResponse,
    FeedbackSummary,
    Glossary,
    Health,
    LessonTeaching,
    LiveModelSettingsRequest,
    LiveModelSettingsResponse,
    ModuleFeedbackRequest,
    Orientation,
    PlatformInfo,
    ProgressExport,
    PublicAssessment,
    RemediationRegistry,
    RunStatus,
    ScenarioRun,
    StageMap,
    StructuredLabRun,
)
from .settings import LiveModelSettingsStore
from .structured import run_structured_lab
from .versions import package_version as _package_version

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPOSITORY_ROOT / ".nornyx-lab" / "academy.db"
DEFAULT_FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serve Vite assets and fall back to index.html for client routes."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        # An unmatched /api path must stay a 404 rather than becoming the SPA
        # shell. This is checked before delegating because `html=True` makes
        # StaticFiles fall back to index.html internally without raising, so a
        # mistyped or removed endpoint returned HTML with status 200 and failed
        # later as an unparseable body instead of a clean error.
        #
        # `path` is unusable for this test: StaticFiles builds it with
        # os.path.normpath, which on Windows yields "api\v1\nope". Read the URL
        # from the scope instead so the check behaves the same on every OS.
        url_path: str = scope.get("path", "")
        if url_path == "/api" or url_path.startswith("/api/"):
            raise StarletteHTTPException(status_code=404, detail="Unknown API endpoint")
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in Path(path).name:
                raise
            return await super().get_response("index.html", scope)


def _feedback_configuration() -> FeedbackConfiguration:
    """Read the non-secret feedback configuration from the environment.

    There is no credential to read. A learner installation is configured with, at
    most, the address of a gateway; GitHub authority lives only in that gateway.
    An unset endpoint is a fully supported state, not a degraded one: feedback
    still works, it simply stays on this computer.
    """

    endpoint = (os.environ.get("NORNYX_FEEDBACK_ENDPOINT") or "").strip() or None
    raw_visibility = (os.environ.get("NORNYX_FEEDBACK_DESTINATION_VISIBILITY") or "").strip()
    try:
        visibility = DestinationVisibility(raw_visibility)
    except ValueError:
        # An installation cannot see how the maintainers configured their intake
        # repository. Unknown is the honest default and the consent copy says so.
        visibility = DestinationVisibility.UNKNOWN
    try:
        timeout = float(os.environ.get("NORNYX_FEEDBACK_TIMEOUT_SECONDS", "10"))
    except ValueError:
        timeout = 10.0
    return FeedbackConfiguration(
        endpoint=endpoint,
        destination_visibility=visibility,
        timeout_seconds=max(1.0, min(timeout, 60.0)),
    )


def _compatibility() -> dict[str, Any]:
    return json.loads(
        files("nornyx_lab.academy.content")
        .joinpath("compatibility.json")
        .read_text(encoding="utf-8")
    )


def _detail(exc: Exception) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def create_app(
    *,
    database_path: str | Path | None = None,
    frontend_dist: str | Path | None = None,
    feedback_configuration: FeedbackConfiguration | None = None,
    feedback_transport: FeedbackTransport | None = None,
) -> FastAPI:
    """Create an independently testable academy service."""

    app = FastAPI(
        title="Nornyx Academy API",
        version="2.0.0",
        description=(
            "Versioned, structured APIs for deterministic AI-governance lessons. "
            "No learner endpoint requires a shell or terminal transcript."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    resolved_database = Path(database_path or os.environ.get("NORNYX_ACADEMY_DB", DEFAULT_DB_PATH))
    app.state.catalog = CurriculumRepository()
    app.state.pedagogy = PedagogyRepository()
    app.state.assessments = AssessmentService()
    # The learner record derives concept mastery from recorded attempts and the
    # concepts each assessment declares it tests; it needs both maps so legacy
    # attempts re-derive honest evidence instead of keeping blanket mastery.
    app.state.progress = SQLiteLearnerRecordRepository(
        resolved_database,
        assessment_concepts={
            assessment_id: app.state.assessments.definition(assessment_id).concepts
            for assessment_id in app.state.assessments.ids()
        },
        module_concepts={module.id: module.concepts for module in app.state.catalog.modules()},
    )
    app.state.live_settings = LiveModelSettingsStore()

    # Learner feedback shares the database file and nothing else. It is
    # constructed after the learner record and reads from it; the learner record
    # has no reference to feedback in either direction, which is what keeps
    # perception out of every competence derivation.
    app.state.feedback_repository = SQLiteFeedbackRepository(resolved_database)
    app.state.feedback = FeedbackService(
        app.state.feedback_repository,
        configuration=feedback_configuration or _feedback_configuration(),
        assessment_outcome=lambda module_id: app.state.progress.assessment_outcome(module_id),
        content_version=app.state.catalog.version,
        transport=feedback_transport,
    )

    def module_ids() -> tuple[str, ...]:
        return tuple(module.id for module in app.state.catalog.modules())

    def dashboard() -> Dashboard:
        return app.state.progress.dashboard(module_ids())

    def progress_map() -> dict[str, Any]:
        return {item.module_id: item for item in dashboard().modules}

    def record_run(result: StructuredLabRun) -> None:
        passed = result.status is RunStatus.COMPLETE and result.completion_eligible
        app.state.progress.record_execution(
            result.module_id,
            passed=passed,
            version_binding={
                "academy": _package_version("nornyx-lab", "2.0.0"),
                "nornyx": _package_version("nornyx", "1.11.0"),
            },
        )
        # Capstone runs additionally record the evidence the advanced gate
        # reads: scaffolding level, scenario, authorship, and eligibility.
        # Unavailable runs (missing framework) are not learner outcomes.
        if result.module_id == "24" and result.status is RunStatus.COMPLETE:
            competence = result.results.get("competence", {})
            app.state.progress.record_capstone_run(
                run_id=result.run_id,
                scenario=str(competence.get("scenario", "customer-remediation")),
                scaffolding=str(competence.get("scaffolding", "guided")),
                completion_eligible=result.completion_eligible,
                learner_authored=bool(competence.get("learner_authored", False)),
            )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get(f"/api/{API_VERSION}/health", response_model=Health, tags=["platform"])
    def health() -> Health:
        return Health()

    @app.get(f"/api/{API_VERSION}/platform", response_model=PlatformInfo, tags=["platform"])
    def platform() -> PlatformInfo:
        compatibility = _compatibility()
        baseline = compatibility["runtime_baseline"]
        audited = compatibility["audited_main"]
        return PlatformInfo(
            academy_version=_package_version("nornyx-lab", "2.0.0"),
            nornyx_runtime_version=_package_version("nornyx", baseline["nornyx_version"]),
            nornyx_audited_main_commit=audited["commit"],
            nornyx_main_delta="; ".join(audited["delta"]),
            adapter_version=_package_version(
                "nornyx-agentic-adapters", baseline["adapter_version"]
            ),
            spi_version=baseline["agentic_spi"],
        )

    @app.get(f"/api/{API_VERSION}/catalog", response_model=CurriculumCatalog, tags=["curriculum"])
    def catalog() -> CurriculumCatalog:
        return app.state.catalog.catalog(progress_map())

    @app.get(
        f"/api/{API_VERSION}/modules/{{module_id}}",
        response_model=CurriculumModule,
        tags=["curriculum"],
    )
    def module(module_id: str) -> Any:
        try:
            return app.state.catalog.module(module_id, progress_map())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc

    # ------------------------------------------------------------- pedagogy
    @app.get(f"/api/{API_VERSION}/orientation", response_model=Orientation, tags=["pedagogy"])
    def orientation() -> Orientation:
        return app.state.pedagogy.orientation()

    @app.get(f"/api/{API_VERSION}/demo/story", tags=["pedagogy"])
    def demo_story() -> dict[str, Any]:
        return app.state.pedagogy.demo_story()

    @app.get(f"/api/{API_VERSION}/glossary", response_model=Glossary, tags=["pedagogy"])
    def glossary() -> Glossary:
        return app.state.pedagogy.glossary()

    @app.get(
        f"/api/{API_VERSION}/remediation",
        response_model=RemediationRegistry,
        tags=["pedagogy"],
    )
    def remediation() -> RemediationRegistry:
        """Authored guidance keyed by diagnostic code.

        Deliberately its own endpoint rather than a field on each diagnostic:
        this is academy teaching material, not a Nornyx runtime decision, and
        the browser labels it as such where it renders.
        """
        return app.state.pedagogy.remediation()

    @app.get(f"/api/{API_VERSION}/stages", response_model=StageMap, tags=["pedagogy"])
    def stages() -> StageMap:
        statuses = {item.module_id: item.status for item in dashboard().modules}
        return app.state.pedagogy.stages(statuses)

    @app.get(
        f"/api/{API_VERSION}/modules/{{module_id}}/teaching",
        response_model=LessonTeaching,
        tags=["pedagogy"],
    )
    def teaching(module_id: str) -> LessonTeaching:
        try:
            return app.state.pedagogy.teaching(module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc

    @app.post(f"/api/{API_VERSION}/demo/run", response_model=ScenarioRun, tags=["scenarios"])
    def demo(options: DemoOptions) -> ScenarioRun:
        try:
            if options.planner_mode == "live":
                result = run_atlas_demo(options, planner=app.state.live_settings.planner())
            else:
                result = run_atlas_demo(options)
        except (RuntimeError, ScenarioUnavailable) as exc:
            raise HTTPException(status_code=503, detail=_detail(exc)) from exc
        app.state.progress.record_execution(
            "F0",
            passed=True,
            version_binding={"scenario": result.scenario_id, "run": result.run_id},
        )
        return result

    @app.post(
        f"/api/{API_VERSION}/labs/{{legacy_id}}/run",
        response_model=StructuredLabRun,
        tags=["scenarios"],
    )
    def legacy_lab(legacy_id: str) -> StructuredLabRun:
        try:
            if legacy_id in {"19", "22", "23"}:
                result = run_advanced_module(legacy_id)
            else:
                result = run_structured_lab(legacy_id, module_id=legacy_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc
        record_run(result)
        return result

    @app.post(
        f"/api/{API_VERSION}/modules/{{module_id}}/run",
        response_model=StructuredLabRun,
        tags=["scenarios"],
    )
    def run_module(
        module_id: str,
        inputs: dict[str, Any] | None = Body(default=None),
    ) -> StructuredLabRun:
        try:
            app.state.catalog.module(module_id)
            if module_id.startswith("F"):
                result = run_foundation(module_id, inputs)
            elif module_id == "24":
                from .capstone import run_capstone

                result = run_capstone(inputs)
            elif module_id in {"19", "22", "23"}:
                result = run_advanced_module(module_id, inputs)
            else:
                result = run_structured_lab(module_id, module_id=module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc
        except (AdvancedInputError, FoundationInputError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc
        record_run(result)
        return result

    @app.get(
        f"/api/{API_VERSION}/assessments/{{assessment_id}}",
        response_model=PublicAssessment,
        tags=["assessments"],
    )
    def assessment(assessment_id: str) -> PublicAssessment:
        try:
            return app.state.assessments.public(assessment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc

    @app.post(
        f"/api/{API_VERSION}/assessments/{{assessment_id}}/submit",
        response_model=AssessmentResult,
        tags=["assessments"],
    )
    def submit_assessment(assessment_id: str, submission: AssessmentSubmission) -> AssessmentResult:
        try:
            result = app.state.assessments.submit(assessment_id, submission)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc
        progress = app.state.progress.record_assessment(
            result,
            answers=submission.answers,
            version_binding={
                "academy": _package_version("nornyx-lab", "2.0.0"),
                "assessment": result.assessment_id,
            },
        )
        # Report what the module still lacks evidence for, so the UI can state
        # partial mastery instead of implying the module's concepts are done.
        return result.model_copy(
            update={"module_concepts_pending": progress.concepts_pending_evidence}
        )

    @app.get(f"/api/{API_VERSION}/progress", response_model=Dashboard, tags=["progress"])
    def get_progress() -> Dashboard:
        return dashboard()

    @app.post(f"/api/{API_VERSION}/progress/reset", response_model=Dashboard, tags=["progress"])
    def reset_progress() -> Dashboard:
        app.state.progress.reset()
        return dashboard()

    @app.get(
        f"/api/{API_VERSION}/progress/export",
        response_model=ProgressExport,
        tags=["progress"],
    )
    def export_progress() -> ProgressExport:
        return app.state.progress.export(module_ids())

    # ------------------------------------------------------- learner feedback
    # Research instrumentation. Every endpoint below writes to feedback tables
    # only, and no response any of them returns is consulted by scoring,
    # completion, mastery, capstone eligibility, or advanced standing.
    #
    # Note what the request models do *not* accept: a score, a status, a version,
    # a competence revision, a session identifier, or a timestamp. The browser
    # states how the lesson felt; the server states everything else.

    @app.get(f"/api/{API_VERSION}/feedback", response_model=FeedbackStatus, tags=["feedback"])
    def feedback_status() -> FeedbackStatus:
        return app.state.feedback.status()

    @app.post(
        f"/api/{API_VERSION}/feedback/modules/{{module_id}}",
        response_model=FeedbackSubmissionResponse,
        tags=["feedback"],
    )
    def submit_module_feedback(
        module_id: str, request: ModuleFeedbackRequest
    ) -> FeedbackSubmissionResponse:
        try:
            app.state.catalog.module(module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc
        return app.state.feedback.submit_module_feedback(module_id, request)

    @app.post(
        f"/api/{API_VERSION}/feedback/course",
        response_model=FeedbackSubmissionResponse,
        tags=["feedback"],
    )
    def submit_course_feedback(request: CourseFeedbackRequest) -> FeedbackSubmissionResponse:
        known = set(module_ids())
        for value in (request.most_helpful_module, request.most_confusing_module):
            if value is not None and value not in known:
                raise HTTPException(status_code=422, detail=f"unknown curriculum module {value!r}")
        # Counted from admissible evidence, module by module, rather than from
        # the dashboard aggregate: the aggregate sums every attempt ever made,
        # including ones the current competence contract no longer admits.
        attempts = sum(
            app.state.progress.assessment_outcome(module_id).attempts for module_id in module_ids()
        )
        return app.state.feedback.submit_course_feedback(request, total_attempts=attempts)

    @app.post(
        f"/api/{API_VERSION}/feedback/consent",
        response_model=FeedbackStatus,
        tags=["feedback"],
    )
    def set_feedback_consent(request: FeedbackConsentRequest) -> FeedbackStatus:
        return app.state.feedback.set_consent(granted=request.granted)

    @app.post(f"/api/{API_VERSION}/feedback/sync", response_model=FeedbackStatus, tags=["feedback"])
    def sync_feedback() -> FeedbackStatus:
        """One bounded delivery attempt, requested explicitly.

        Never a retry loop: a learner pressing "try again" gets one attempt and
        an honest answer, not a request that blocks behind a backoff schedule.
        """

        return app.state.feedback.sync_now()

    @app.delete(
        f"/api/{API_VERSION}/feedback",
        response_model=FeedbackDeletionResponse,
        tags=["feedback"],
    )
    def delete_feedback() -> FeedbackDeletionResponse:
        """Delete local feedback only. Progress is untouched, and so is anything already sent."""

        return app.state.feedback.delete_local_feedback()

    @app.get(
        f"/api/{API_VERSION}/feedback/summary",
        response_model=FeedbackSummary,
        tags=["feedback"],
    )
    def feedback_summary() -> FeedbackSummary:
        """Counts for this installation. Maintainer instrumentation, not a learner view."""

        return app.state.feedback.summary()

    @app.get(
        f"/api/{API_VERSION}/contracts",
        response_model=tuple[ContractSummary, ...],
        tags=["contracts"],
    )
    def contracts() -> tuple[ContractSummary, ...]:
        return list_contracts()

    @app.get(
        f"/api/{API_VERSION}/contracts/{{contract_id}}",
        response_model=ContractDetail,
        tags=["contracts"],
    )
    def contract(contract_id: str) -> ContractDetail:
        try:
            return get_contract(contract_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=_detail(exc)) from exc

    @app.post(
        f"/api/{API_VERSION}/contracts/workbench",
        response_model=ContractValidation,
        tags=["contracts"],
    )
    def contract_workbench(request: ContractWorkbenchRequest) -> ContractValidation:
        try:
            return validate_workbench(request)
        except ContractWorkbenchError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": str(exc), "path": exc.path},
            ) from exc

    @app.get(
        f"/api/{API_VERSION}/settings/live",
        response_model=LiveModelSettingsResponse,
        tags=["settings"],
    )
    def live_settings() -> LiveModelSettingsResponse:
        return app.state.live_settings.response()

    @app.put(
        f"/api/{API_VERSION}/settings/live",
        response_model=LiveModelSettingsResponse,
        tags=["settings"],
    )
    def configure_live_settings(
        request: LiveModelSettingsRequest,
    ) -> LiveModelSettingsResponse:
        try:
            return app.state.live_settings.configure(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc

    @app.get(
        f"/api/{API_VERSION}/capstone",
        response_model=CapstoneDefinition,
        tags=["capstone"],
    )
    def capstone() -> CapstoneDefinition:
        from .capstone import capstone_template

        template = dict(capstone_template())
        template["status"] = app.state.progress.get("24").status
        return CapstoneDefinition.model_validate(template)

    @app.post(
        f"/api/{API_VERSION}/capstone/run",
        response_model=StructuredLabRun,
        tags=["capstone"],
    )
    def execute_capstone(request: CapstoneRunRequest) -> StructuredLabRun:
        from .capstone import CapstoneInputError, run_capstone

        try:
            result = run_capstone(request.model_dump(mode="json", exclude_none=True))
        except CapstoneInputError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc
        record_run(result)
        return result

    resolved_frontend = Path(
        frontend_dist or os.environ.get("NORNYX_ACADEMY_FRONTEND_DIST", DEFAULT_FRONTEND_DIST)
    )
    if resolved_frontend.is_dir() and (resolved_frontend / "index.html").is_file():
        # Registered last so the typed API and docs retain precedence. html=True
        # provides browser-history fallback for React routes.
        app.mount("/", SPAStaticFiles(directory=resolved_frontend, html=True), name="academy-ui")

    return app


app = create_app()

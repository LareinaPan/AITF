import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.api_endpoints import router as api_endpoints_router
from app.api.auth import router as auth_router
from app.api.fc_experience_cases import router as fc_experience_cases_router
from app.api.fc_export import router as fc_export_router
from app.api.fc_generation import router as fc_generation_router
from app.api.fc_generation_batches import router as fc_generation_batches_router
from app.api.fc_projects import router as fc_projects_router
from app.api.fc_requirement_docs import router as fc_requirement_docs_router
from app.api.fc_test_cases import router as fc_test_cases_router
from app.api.dashboard import router as dashboard_router
from app.api.environments import router as environments_router
from app.api.openapi import router as openapi_router
from app.api.projects import router as projects_router
from app.api.pt_projects import router as pt_projects_router
from app.api.pt_runs import router as pt_runs_router
from app.api.pt_scenarios import router as pt_scenarios_router
from app.api.pt_scripts import router as pt_scripts_router
from app.api.test_cases import router as test_cases_router
from app.api.test_plans import router as test_plans_router
from app.config import get_settings
from app.scheduler.plan_jobs import start_plan_scheduler
from app.services.allure_service import ALLURE_REPORTS_DIR, ensure_storage_dirs, resolve_allure_cli
from app.services.pt_run_recovery_service import recover_orphaned_running_runs

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    recover_orphaned_running_runs()
    allure_cli = resolve_allure_cli()
    if allure_cli is None:
        logging.getLogger(__name__).warning(
            "Allure CLI is not available; test plan reports will use fallback HTML. "
            "Install Allure or set ALLURE_CLI in .env (Docker: rebuild backend image)."
        )
    else:
        logging.getLogger(__name__).info("Allure CLI available at %s", allure_cli)
    scheduler = start_plan_scheduler()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="AITF API",
    description="AI Test Framework — API Testing Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(fc_projects_router, prefix="/api/v1/fc-projects", tags=["fc-projects"])
app.include_router(pt_projects_router, prefix="/api/v1/pt-projects", tags=["pt-projects"])
app.include_router(
    pt_scenarios_router,
    prefix="/api/v1/pt-projects/{project_id}/scenarios",
    tags=["pt-scenarios"],
)
app.include_router(
    pt_scripts_router,
    prefix="/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script",
    tags=["pt-scripts"],
)
app.include_router(
    pt_runs_router,
    prefix="/api/v1/pt-projects/{project_id}",
    tags=["pt-runs"],
)
app.include_router(
    fc_generation_router,
    prefix="/api/v1/fc-projects/{fc_project_id}",
    tags=["fc-generation"],
)
app.include_router(
    fc_requirement_docs_router,
    prefix="/api/v1/fc-projects/{fc_project_id}/docs",
    tags=["fc-requirement-docs"],
)
app.include_router(
    fc_experience_cases_router,
    prefix="/api/v1/fc-projects/{fc_project_id}/experience-cases",
    tags=["fc-experience-cases"],
)
app.include_router(
    fc_test_cases_router,
    prefix="/api/v1/fc-projects/{fc_project_id}/cases",
    tags=["fc-test-cases"],
)
app.include_router(
    fc_export_router,
    prefix="/api/v1/fc-projects/{fc_project_id}/export",
    tags=["fc-export"],
)
app.include_router(
    fc_generation_batches_router,
    prefix="/api/v1/fc-projects/{fc_project_id}/batches",
    tags=["fc-generation-batches"],
)
app.include_router(
    test_cases_router,
    prefix="/api/v1/projects/{project_id}/cases",
    tags=["test-cases"],
)
app.include_router(
    test_plans_router,
    prefix="/api/v1/projects/{project_id}/plans",
    tags=["test-plans"],
)
app.include_router(
    api_endpoints_router,
    prefix="/api/v1/projects/{project_id}/apis",
    tags=["api-endpoints"],
)
app.include_router(
    openapi_router,
    prefix="/api/v1/projects/{project_id}/openapi",
    tags=["openapi"],
)
app.include_router(environments_router, prefix="/api/v1/environments", tags=["environments"])

ALLURE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(ALLURE_REPORTS_DIR)), name="reports")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health")
def api_health_check() -> dict[str, str]:
    return {"status": "ok", "service": "aitf-api"}

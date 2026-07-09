"""Fast deletion for performance test projects and related rows."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.pt_project import PtProject
from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.services.pt_jmx_parser import delete_pt_jmx_file, pt_upload_dir

logger = logging.getLogger(__name__)


class PtProjectDeleteError(LookupError):
    """Raised when a performance project cannot be deleted."""


class PtProjectRunningError(PtProjectDeleteError):
    """Raised when a load test is still running for the project."""


def delete_pt_project(db: Session, project_id: uuid.UUID) -> None:
    """Delete a PT project and all related rows without ORM cascade loading."""
    project = db.get(PtProject, project_id)
    if project is None:
        raise PtProjectDeleteError("Performance project not found")

    running_count = db.scalar(
        select(func.count())
        .select_from(PtRun)
        .where(
            PtRun.pt_project_id == project_id,
            PtRun.status == PtRunStatus.RUNNING.value,
        )
    ) or 0
    if running_count > 0:
        raise PtProjectRunningError("Cannot delete project while a load test is running")

    file_paths = list(
        db.scalars(
            select(PtScript.file_path)
            .join(PtScenario, PtScript.pt_scenario_id == PtScenario.id)
            .where(
                PtScenario.pt_project_id == project_id,
                PtScript.file_path.isnot(None),
            )
        ).all()
    )

    run_ids = select(PtRun.id).where(PtRun.pt_project_id == project_id)
    scenario_ids = select(PtScenario.id).where(PtScenario.pt_project_id == project_id)

    db.execute(delete(PtRunErrorLog).where(PtRunErrorLog.pt_run_id.in_(run_ids)))
    db.execute(delete(PtRunMetricPoint).where(PtRunMetricPoint.pt_run_id.in_(run_ids)))
    db.execute(delete(PtRun).where(PtRun.pt_project_id == project_id))
    db.execute(delete(PtScript).where(PtScript.pt_scenario_id.in_(scenario_ids)))
    db.execute(delete(PtScenario).where(PtScenario.pt_project_id == project_id))
    db.execute(delete(PtProject).where(PtProject.id == project_id))
    db.commit()

    for file_path in file_paths:
        delete_pt_jmx_file(file_path)

    upload_dir = pt_upload_dir(project_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)

    logger.info("Deleted performance project %s", project_id)

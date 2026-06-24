import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.test_plan import PlanRun
from app.services.allure_service import get_reports_dir, get_results_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportCleanupSummary:
    deleted_runs: int
    deleted_directories: int


def delete_plan_run_artifacts(run_id: uuid.UUID) -> int:
    deleted_directories = 0
    for directory in (get_results_dir(run_id), get_reports_dir(run_id)):
        if not directory.exists():
            continue
        shutil.rmtree(directory)
        deleted_directories += 1
    return deleted_directories


def cleanup_expired_plan_runs(
    db: Session,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> ReportCleanupSummary:
    days = retention_days if retention_days is not None else get_settings().report_retention_days
    reference_time = now or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    cutoff = reference_time - timedelta(days=days)

    expired_runs = list(
        db.scalars(
            select(PlanRun)
            .where(PlanRun.created_at < cutoff)
            .order_by(PlanRun.created_at),
        ).all(),
    )

    deleted_directories = 0
    for plan_run in expired_runs:
        deleted_directories += delete_plan_run_artifacts(plan_run.id)
        db.delete(plan_run)

    if expired_runs:
        db.commit()
        logger.info(
            "Report cleanup removed %s plan run(s) older than %s days",
            len(expired_runs),
            days,
        )

    return ReportCleanupSummary(
        deleted_runs=len(expired_runs),
        deleted_directories=deleted_directories,
    )

import logging
import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.test_plan import TestPlan
from app.scheduler.pt_run_cleanup_jobs import register_pt_run_cleanup_job
from app.scheduler.report_cleanup_jobs import register_report_cleanup_job
from app.services.cron_validator import build_plan_cron_trigger
from app.services.plan_execution_service import execute_test_plan

logger = logging.getLogger(__name__)

PLAN_JOB_PREFIX = "test_plan:"


def get_session_factory() -> sessionmaker:
    from app.database import engine

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _plan_job_id(plan_id: uuid.UUID) -> str:
    return f"{PLAN_JOB_PREFIX}{plan_id}"


def run_scheduled_plan(plan_id: uuid.UUID) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            execute_test_plan(session, plan_id, trigger="cron")
        except Exception:
            logger.exception("Scheduled plan execution failed: plan_id=%s", plan_id)
            session.rollback()


def sync_plan_scheduler_jobs(scheduler: BackgroundScheduler, db: Session) -> None:
    enabled_plans = list(
        db.scalars(
            select(TestPlan).where(
                TestPlan.is_enabled.is_(True),
                TestPlan.cron_expression.is_not(None),
            )
        ).all()
    )
    enabled_ids = {plan.id for plan in enabled_plans}

    for job in scheduler.get_jobs():
        if job.id.startswith(PLAN_JOB_PREFIX):
            plan_id = uuid.UUID(job.id.removeprefix(PLAN_JOB_PREFIX))
            if plan_id not in enabled_ids:
                scheduler.remove_job(job.id)

    for plan in enabled_plans:
        if not plan.cron_expression:
            continue
        job_id = _plan_job_id(plan.id)
        trigger = build_plan_cron_trigger(plan.cron_expression)
        scheduler.add_job(
            run_scheduled_plan,
            trigger=trigger,
            id=job_id,
            args=[plan.id],
            replace_existing=True,
        )


def start_plan_scheduler() -> BackgroundScheduler:
    from app.config import get_settings

    scheduler = BackgroundScheduler(timezone=get_settings().scheduler_timezone)
    session_factory = get_session_factory()
    with session_factory() as session:
        sync_plan_scheduler_jobs(scheduler, session)
    register_report_cleanup_job(scheduler)
    register_pt_run_cleanup_job(scheduler)
    scheduler.start()
    return scheduler

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.report_cleanup_service import cleanup_expired_plan_runs

logger = logging.getLogger(__name__)

REPORT_CLEANUP_JOB_ID = "report_cleanup"


def _get_session_factory():
    from app.scheduler.plan_jobs import get_session_factory

    return get_session_factory()


def run_report_cleanup() -> None:
    session_factory = _get_session_factory()
    with session_factory() as session:
        try:
            summary = cleanup_expired_plan_runs(session)
            logger.info(
                "Scheduled report cleanup finished: runs=%s directories=%s",
                summary.deleted_runs,
                summary.deleted_directories,
            )
        except Exception:
            logger.exception("Scheduled report cleanup failed")
            session.rollback()


def register_report_cleanup_job(scheduler: BackgroundScheduler) -> None:
    scheduler.add_job(
        run_report_cleanup,
        trigger="cron",
        hour=3,
        minute=0,
        id=REPORT_CLEANUP_JOB_ID,
        replace_existing=True,
    )

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.pt_run_cleanup_service import cleanup_expired_pt_runs

logger = logging.getLogger(__name__)

PT_RUN_CLEANUP_JOB_ID = "pt_run_cleanup"


def _get_session_factory():
    from app.scheduler.plan_jobs import get_session_factory

    return get_session_factory()


def run_pt_run_cleanup() -> None:
    session_factory = _get_session_factory()
    with session_factory() as session:
        try:
            summary = cleanup_expired_pt_runs(session)
            logger.info(
                "Scheduled PT run cleanup finished: runs=%s",
                summary.deleted_runs,
            )
        except Exception:
            logger.exception("Scheduled PT run cleanup failed")
            session.rollback()


def register_pt_run_cleanup_job(scheduler: BackgroundScheduler) -> None:
    scheduler.add_job(
        run_pt_run_cleanup,
        trigger="cron",
        hour=3,
        minute=30,
        id=PT_RUN_CLEANUP_JOB_ID,
        replace_existing=True,
    )

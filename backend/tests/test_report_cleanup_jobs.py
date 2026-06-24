from unittest.mock import MagicMock, patch

from app.scheduler.report_cleanup_jobs import REPORT_CLEANUP_JOB_ID, register_report_cleanup_job


def test_register_report_cleanup_job() -> None:
    scheduler = MagicMock()
    register_report_cleanup_job(scheduler)

    scheduler.add_job.assert_called_once()
    kwargs = scheduler.add_job.call_args.kwargs
    assert kwargs["id"] == REPORT_CLEANUP_JOB_ID
    assert kwargs["trigger"] == "cron"
    assert kwargs["hour"] == 3
    assert kwargs["minute"] == 0


@patch("app.scheduler.report_cleanup_jobs._get_session_factory")
@patch("app.scheduler.report_cleanup_jobs.cleanup_expired_plan_runs")
def test_run_report_cleanup(mock_cleanup, mock_get_session_factory) -> None:
    from app.scheduler.report_cleanup_jobs import run_report_cleanup

    session = MagicMock()
    mock_get_session_factory.return_value.return_value.__enter__.return_value = session
    mock_get_session_factory.return_value.return_value.__exit__.return_value = None
    mock_cleanup.return_value.deleted_runs = 2
    mock_cleanup.return_value.deleted_directories = 4

    run_report_cleanup()

    mock_cleanup.assert_called_once_with(session)

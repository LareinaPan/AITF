from unittest.mock import MagicMock, patch

from app.scheduler.pt_run_cleanup_jobs import PT_RUN_CLEANUP_JOB_ID, register_pt_run_cleanup_job


def test_register_pt_run_cleanup_job() -> None:
    scheduler = MagicMock()
    register_pt_run_cleanup_job(scheduler)

    scheduler.add_job.assert_called_once()
    kwargs = scheduler.add_job.call_args.kwargs
    assert kwargs["id"] == PT_RUN_CLEANUP_JOB_ID
    assert kwargs["trigger"] == "cron"
    assert kwargs["hour"] == 3
    assert kwargs["minute"] == 30


@patch("app.scheduler.pt_run_cleanup_jobs._get_session_factory")
@patch("app.scheduler.pt_run_cleanup_jobs.cleanup_expired_pt_runs")
def test_run_pt_run_cleanup(mock_cleanup, mock_get_session_factory) -> None:
    from app.scheduler.pt_run_cleanup_jobs import run_pt_run_cleanup

    session = MagicMock()
    mock_get_session_factory.return_value.return_value.__enter__.return_value = session
    mock_get_session_factory.return_value.return_value.__exit__.return_value = None
    mock_cleanup.return_value.deleted_runs = 3

    run_pt_run_cleanup()

    mock_cleanup.assert_called_once_with(session)

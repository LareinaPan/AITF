import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_project import PtProject
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.models.user import User
from app.services.pt_run_cleanup_service import cleanup_expired_pt_runs


def _create_pt_run(session) -> tuple[PtProject, PtRun]:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()

    project = PtProject(name="Cleanup PT Project", created_by=user.id)
    session.add(project)
    session.flush()

    scenario = PtScenario(pt_project_id=project.id, name="Cleanup Scenario")
    session.add(scenario)
    session.flush()

    script = PtScript(pt_scenario_id=scenario.id)
    session.add(script)
    session.flush()

    run = PtRun(
        pt_project_id=project.id,
        pt_scenario_id=scenario.id,
        scenario_name_snapshot=scenario.name,
        status=PtRunStatus.COMPLETED.value,
        config_snapshot_json={
            "max_concurrency": script.max_concurrency,
            "ramp_up_seconds": script.ramp_up_seconds,
            "stop_mode": script.stop_mode,
            "duration_seconds": 60,
            "samplers": [],
        },
        triggered_by=user.id,
    )
    session.add(run)
    session.flush()

    session.add(
        PtRunMetricPoint(
            pt_run_id=run.id,
            sampler_key="sampler-001",
            recorded_at=datetime.now(timezone.utc),
            qps=10.0,
            avg_rt_ms=50.0,
            error_rate_percent=0.0,
        )
    )
    session.add(
        PtRunErrorLog(
            pt_run_id=run.id,
            occurred_at=datetime.now(timezone.utc),
            sampler_key="sampler-001",
            sampler_name="Demo",
            status_code=500,
            error_type="http_error",
            message="HTTP 500",
        )
    )
    session.commit()
    session.refresh(run)
    return project, run


def _set_started_at(session, run: PtRun, started_at: datetime) -> None:
    run.started_at = started_at
    session.commit()


def test_cleanup_deletes_expired_runs_and_related_rows(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        _, expired_run = _create_pt_run(session)
        _set_started_at(
            session,
            expired_run,
            datetime.now(timezone.utc) - timedelta(days=31),
        )

        summary = cleanup_expired_pt_runs(session, retention_days=30)

        assert summary.deleted_runs == 1
        assert session.get(PtRun, expired_run.id) is None
        metric_count = session.scalar(
            select(func.count())
            .select_from(PtRunMetricPoint)
            .where(PtRunMetricPoint.pt_run_id == expired_run.id)
        )
        error_count = session.scalar(
            select(func.count())
            .select_from(PtRunErrorLog)
            .where(PtRunErrorLog.pt_run_id == expired_run.id)
        )
        assert metric_count == 0
        assert error_count == 0

    engine.dispose()


def test_cleanup_preserves_recent_runs(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        _, recent_run = _create_pt_run(session)
        _set_started_at(
            session,
            recent_run,
            datetime.now(timezone.utc) - timedelta(days=10),
        )

        summary = cleanup_expired_pt_runs(session, retention_days=30)

        assert summary.deleted_runs == 0
        assert session.get(PtRun, recent_run.id) is not None

    engine.dispose()


def test_cleanup_only_removes_expired_runs(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)

    with session_factory() as session:
        _, expired_run = _create_pt_run(session)
        _, recent_run = _create_pt_run(session)
        _set_started_at(session, expired_run, now - timedelta(days=40))
        _set_started_at(session, recent_run, now - timedelta(days=5))

        summary = cleanup_expired_pt_runs(session, retention_days=30, now=now)

        assert summary.deleted_runs == 1
        remaining_ids = set(session.scalars(select(PtRun.id)).all())
        assert recent_run.id in remaining_ids
        assert expired_run.id not in remaining_ids

    engine.dispose()

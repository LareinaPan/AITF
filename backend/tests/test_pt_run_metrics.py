import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.models.user import User


def test_pt_run_metric_and_error_tables_exist_after_migration(migrated_db: str) -> None:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "pt_run_metric_points" in table_names
    assert "pt_run_error_logs" in table_names

    metric_columns = {
        column["name"] for column in inspector.get_columns("pt_run_metric_points")
    }
    assert {
        "id",
        "pt_run_id",
        "sampler_key",
        "recorded_at",
        "qps",
        "avg_rt_ms",
        "rt_p95_ms",
        "rt_p99_ms",
        "error_rate_percent",
    }.issubset(metric_columns)

    error_columns = {column["name"] for column in inspector.get_columns("pt_run_error_logs")}
    assert {
        "id",
        "pt_run_id",
        "occurred_at",
        "sampler_key",
        "sampler_name",
        "status_code",
        "error_type",
        "message",
    }.issubset(error_columns)

    engine.dispose()


def test_create_pt_run_metric_point_and_error_log(migrated_db: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db: Session = session_factory()

    try:
        user = User(
            id=uuid.uuid4(),
            username=f"pt_metric_user_{uuid.uuid4().hex[:8]}",
            password_hash="hashed",
        )
        db.add(user)
        db.flush()

        from app.models.pt_project import PtProject

        project = PtProject(
            id=uuid.uuid4(),
            name="Metric Test Project",
            created_by=user.id,
        )
        db.add(project)
        db.flush()

        scenario = PtScenario(
            id=uuid.uuid4(),
            pt_project_id=project.id,
            name="Metric Test Scenario",
        )
        db.add(scenario)
        db.flush()

        script = PtScript(pt_scenario_id=scenario.id)
        db.add(script)
        db.flush()

        run = PtRun(
            id=uuid.uuid4(),
            pt_project_id=project.id,
            pt_scenario_id=scenario.id,
            scenario_name_snapshot=scenario.name,
            status=PtRunStatus.RUNNING.value,
            config_snapshot_json={
                "max_concurrency": script.max_concurrency,
                "ramp_up_seconds": script.ramp_up_seconds,
                "stop_mode": script.stop_mode,
                "duration_seconds": 60,
                "samplers": [],
            },
            triggered_by=user.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.flush()

        metric_point = PtRunMetricPoint(
            id=uuid.uuid4(),
            pt_run_id=run.id,
            sampler_key="sampler-001",
            recorded_at=datetime.now(timezone.utc),
            qps=12.5,
            avg_rt_ms=45.2,
            rt_p95_ms=80.0,
            rt_p99_ms=95.0,
            error_rate_percent=1.5,
        )
        error_log = PtRunErrorLog(
            id=uuid.uuid4(),
            pt_run_id=run.id,
            occurred_at=datetime.now(timezone.utc),
            sampler_key="sampler-001",
            sampler_name="List Users",
            status_code=500,
            error_type="http_error",
            message="HTTP 500",
        )
        db.add(metric_point)
        db.add(error_log)
        db.commit()

        saved_run = db.get(PtRun, run.id)
        assert saved_run is not None
        assert len(saved_run.metric_points) == 1
        assert len(saved_run.error_logs) == 1
        assert saved_run.metric_points[0].sampler_key == "sampler-001"
        assert saved_run.error_logs[0].error_type == "http_error"
    finally:
        db.close()
        engine.dispose()

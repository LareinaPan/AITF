import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.models.user import User
from app.services.pt_load_engine import LoadSampleResult
from app.services.pt_metrics_aggregator import PtMetricsAggregator, percentile


def _session(migrated_db: str) -> tuple[Session, object]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_factory(), engine


def _seed_user_project_scenario(db: Session) -> tuple[User, uuid.UUID, PtScenario, PtScript]:
    from app.models.pt_project import PtProject

    user = User(
        id=uuid.uuid4(),
        username=f"pt_run_user_{uuid.uuid4().hex[:8]}",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    project = PtProject(
        id=uuid.uuid4(),
        name="Run Test Project",
        created_by=user.id,
    )
    db.add(project)
    db.flush()

    scenario = PtScenario(
        id=uuid.uuid4(),
        pt_project_id=project.id,
        name="Run Test Scenario",
    )
    db.add(scenario)
    db.flush()

    script = PtScript(pt_scenario_id=scenario.id)
    db.add(script)
    db.flush()
    return user, project.id, scenario, script


def _seed_completed_run_bundle(
    db: Session,
) -> tuple[uuid.UUID, uuid.UUID, PtRun]:
    user, project_id, scenario, script = _seed_user_project_scenario(db)
    started_at = datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(seconds=20)

    run = PtRun(
        id=uuid.uuid4(),
        pt_project_id=project_id,
        pt_scenario_id=scenario.id,
        scenario_name_snapshot=scenario.name,
        status=PtRunStatus.COMPLETED.value,
        stop_reason="duration_reached",
        config_snapshot_json={
            "max_concurrency": script.max_concurrency,
            "ramp_up_seconds": script.ramp_up_seconds,
            "stop_mode": script.stop_mode,
            "duration_seconds": 60,
            "samplers": [],
        },
        summary_json={
            "run_id": str(uuid.uuid4()),
            "status": "completed",
            "stop_reason": "duration_reached",
            "interfaces": [
                {
                    "sampler_key": "sampler-001",
                    "name": "Login API",
                    "rt_p99_ms": 99.0,
                    "rt_p95_ms": 95.0,
                    "qps": 2.5,
                    "error_rate_percent": 25.0,
                    "total_requests": 50,
                    "failed_requests": 12,
                }
            ],
        },
        triggered_by=user.id,
        started_at=started_at,
        ended_at=ended_at,
    )
    db.add(run)
    db.flush()

    db.add(
        PtRunMetricPoint(
            pt_run_id=run.id,
            sampler_key="sampler-001",
            recorded_at=started_at + timedelta(seconds=3),
            qps=8.0,
            avg_rt_ms=40.0,
            rt_p95_ms=90.0,
            rt_p99_ms=98.0,
            error_rate_percent=10.0,
        )
    )
    db.add(
        PtRunMetricPoint(
            pt_run_id=run.id,
            sampler_key="sampler-001",
            recorded_at=started_at + timedelta(seconds=6),
            qps=10.0,
            avg_rt_ms=45.0,
            rt_p95_ms=95.0,
            rt_p99_ms=99.0,
            error_rate_percent=25.0,
        )
    )
    db.add(
        PtRunErrorLog(
            pt_run_id=run.id,
            occurred_at=started_at + timedelta(seconds=4),
            sampler_key="sampler-001",
            sampler_name="Login API",
            status_code=500,
            error_type="http_error",
            message="HTTP 500",
        )
    )
    db.commit()
    db.refresh(run)
    return project_id, run.id, run


def test_pt_runs_table_exists_after_migration(migrated_db: str) -> None:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)
    assert "pt_runs" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("pt_runs")}
    assert {
        "id",
        "pt_project_id",
        "pt_scenario_id",
        "scenario_name_snapshot",
        "status",
        "stop_reason",
        "config_snapshot_json",
        "summary_json",
        "error_message",
        "triggered_by",
        "started_at",
        "ended_at",
    }.issubset(columns)
    engine.dispose()


def test_create_pt_run_record(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        user, project_id, scenario, script = _seed_user_project_scenario(db)
        run = PtRun(
            id=uuid.uuid4(),
            pt_project_id=project_id,
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
        db.commit()

        saved = db.get(PtRun, run.id)
        assert saved is not None
        assert saved.status == PtRunStatus.RUNNING.value
        assert saved.scenario_name_snapshot == "Run Test Scenario"
        assert saved.config_snapshot_json["max_concurrency"] == 10
    finally:
        db.close()
        engine.dispose()


def test_percentile_nearest_rank_p95_p99() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(values, 95) == 100.0
    assert percentile(values, 99) == 100.0
    assert percentile(values, 50) == 50.0


def test_summary_json_includes_p95_p99_qps_and_error_rate() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)
    for latency, success in (
        (100.0, True),
        (200.0, True),
        (300.0, True),
        (400.0, False),
        (500.0, False),
    ):
        aggregator.record(
            LoadSampleResult(
                sampler_key="sampler-001",
                sampler_name="Login API",
                status_code=200 if success else 500,
                response_time_ms=latency,
                success=success,
                error_type=None if success else "http_error",
                message=None,
                occurred_at=datetime.now(timezone.utc),
            )
        )

    started_at = datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 7, 3, 10, 0, 10, tzinfo=timezone.utc)
    summary = aggregator.build_summary_json(
        run_id=uuid.uuid4(),
        status="completed",
        started_at=started_at,
        ended_at=ended_at,
        stop_reason="duration_reached",
    )
    interface = summary["interfaces"][0]
    assert interface["rt_p95_ms"] == 500.0
    assert interface["rt_p99_ms"] == 500.0
    assert interface["qps"] == 0.5
    assert interface["error_rate_percent"] == 40.0


def test_api_get_run_returns_summary_percentiles(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id, run_id, _ = _seed_completed_run_bundle(db)
    finally:
        db.close()
        engine.dispose()

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    interface = payload["summary_json"]["interfaces"][0]
    assert interface["rt_p95_ms"] == 95.0
    assert interface["rt_p99_ms"] == 99.0
    assert interface["qps"] == 2.5
    assert interface["error_rate_percent"] == 25.0


def test_api_get_run_metrics_returns_ordered_time_series(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id, run_id, run = _seed_completed_run_bundle(db)
        since = (run.started_at + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    finally:
        db.close()
        engine.dispose()

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/metrics",
        headers=auth_headers,
        params={"sampler_key": "sampler-001", "since": since},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["qps"] == 10.0
    assert items[0]["rt_p95_ms"] == 95.0
    assert items[0]["rt_p99_ms"] == 99.0


def test_api_get_run_errors_returns_failed_requests(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id, run_id, _ = _seed_completed_run_bundle(db)
    finally:
        db.close()
        engine.dispose()

    latest_response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
        headers=auth_headers,
        params={"latest": 10},
    )
    assert latest_response.status_code == 200
    latest_items = latest_response.json()["items"]
    assert len(latest_items) == 1
    assert latest_items[0]["status_code"] == 500
    assert latest_items[0]["error_type"] == "http_error"

    page_response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
        headers=auth_headers,
        params={"page": 1, "page_size": 20},
    )
    assert page_response.status_code == 200
    page_payload = page_response.json()
    assert page_payload["total"] == 1
    assert page_payload["items"][0]["sampler_name"] == "Login API"


def test_api_list_runs_supports_status_filter(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id, run_id, _ = _seed_completed_run_bundle(db)
    finally:
        db.close()
        engine.dispose()

    completed_response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs",
        headers=auth_headers,
        params={"status": "completed"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["total"] == 1
    assert completed_response.json()["items"][0]["id"] == str(run_id)

    running_response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs",
        headers=auth_headers,
        params={"status": "running"},
    )
    assert running_response.status_code == 200
    assert running_response.json()["total"] == 0

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import app.services.pt_run_orchestrator as pt_run_orchestrator
from app.models.pt_project import PtProject
from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript, PtScriptParseStatus, PtScriptStopMode
from app.models.user import User
from app.services.pt_load_engine import LoadSampleResult
from app.services.pt_metrics_aggregator import MetricSnapshot, PtMetricsAggregator
from app.services.pt_run_orchestrator import (
    PtRunConflictError,
    PtRunNotRunningError,
    PtRunOrchestratorError,
    acquire_run_slot,
    build_config_snapshot_from_script,
    cancel_load_test,
    find_global_running_run,
    flush_sampled_error_logs,
    persist_error_log,
    persist_metric_snapshots,
    release_run_slot,
    start_load_test,
    validate_script_ready_for_run,
)


@pytest.fixture(autouse=True)
def reset_orchestrator_state() -> None:
    pt_run_orchestrator._running_run_id = None
    pt_run_orchestrator._active_aggregators.clear()
    pt_run_orchestrator._run_sidecars.clear()
    yield
    pt_run_orchestrator._running_run_id = None
    pt_run_orchestrator._active_aggregators.clear()
    pt_run_orchestrator._run_sidecars.clear()


def _session(migrated_db: str) -> tuple[Session, any]:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_factory(), engine


def _seed_run(db: Session) -> tuple[PtRun, PtScript]:
    user = User(
        id=uuid.uuid4(),
        username=f"orch_user_{uuid.uuid4().hex[:8]}",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    project = PtProject(id=uuid.uuid4(), name="Orch Project", created_by=user.id)
    db.add(project)
    db.flush()

    scenario = PtScenario(
        id=uuid.uuid4(),
        pt_project_id=project.id,
        name="Orch Scenario",
    )
    db.add(scenario)
    db.flush()

    script = PtScript(
        pt_scenario_id=scenario.id,
        parse_status=PtScriptParseStatus.SUCCESS.value,
        parsed_plan_json={
            "samplers": [
                {
                    "key": "sampler-001",
                    "name": "List Users",
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/users",
                    "headers": [],
                    "has_variables": False,
                }
            ],
            "thread_groups": [],
            "parse_warnings": [],
        },
        max_concurrency=2,
        ramp_up_seconds=0,
        stop_mode=PtScriptStopMode.DURATION.value,
        duration_seconds=30,
    )
    db.add(script)
    db.flush()

    run = PtRun(
        id=uuid.uuid4(),
        pt_project_id=project.id,
        pt_scenario_id=scenario.id,
        scenario_name_snapshot=scenario.name,
        status=PtRunStatus.RUNNING.value,
        config_snapshot_json=build_config_snapshot_from_script(script),
        triggered_by=user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, script


def test_build_config_snapshot_from_script() -> None:
    script = PtScript(
        pt_scenario_id=uuid.uuid4(),
        parse_status=PtScriptParseStatus.SUCCESS.value,
        parsed_plan_json={
            "samplers": [{"key": "sampler-001", "name": "A", "method": "GET", "url": "http://x"}]
        },
        max_concurrency=20,
        ramp_up_seconds=5,
        stop_mode=PtScriptStopMode.REQUEST_LIMIT.value,
        default_max_requests=500,
        sampler_limits_json={"sampler-001": 100},
    )

    snapshot = build_config_snapshot_from_script(script)
    assert snapshot["max_concurrency"] == 20
    assert snapshot["stop_mode"] == "request_limit"
    assert snapshot["default_max_requests"] == 500
    assert snapshot["sampler_limits"] == {"sampler-001": 100}
    assert len(snapshot["samplers"]) == 1


def test_validate_script_ready_for_run_rejects_unparsed_script() -> None:
    script = PtScript(
        pt_scenario_id=uuid.uuid4(),
        parse_status=PtScriptParseStatus.PENDING.value,
    )
    with pytest.raises(PtRunOrchestratorError, match="parsed successfully"):
        validate_script_ready_for_run(script)


def test_acquire_run_slot_conflict(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        run, _ = _seed_run(db)

        async def _run() -> None:
            await acquire_run_slot(run.id, db)
            with pytest.raises(PtRunConflictError):
                await acquire_run_slot(uuid.uuid4(), db)
            await release_run_slot(run.id)

        asyncio.run(_run())
    finally:
        db.close()
        engine.dispose()


def test_find_global_running_run(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        run, _ = _seed_run(db)
        assert find_global_running_run(db) is not None
        assert find_global_running_run(db).id == run.id
    finally:
        db.close()
        engine.dispose()


def test_start_load_test_finalizes_completed(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id

        async def _run() -> None:
            with patch("app.services.pt_run_orchestrator.PtLoadEngine") as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = AsyncMock()
                mock_engine.stop_reason = PtRunStopReason.DURATION_REACHED.value
                await start_load_test(run_id)

        asyncio.run(_run())

        db.expire_all()
        saved = db.get(PtRun, run_id)
        assert saved is not None
        assert saved.status == PtRunStatus.COMPLETED.value
        assert saved.stop_reason == PtRunStopReason.DURATION_REACHED.value
        assert saved.summary_json is not None
        assert saved.ended_at is not None
    finally:
        db.close()
        engine.dispose()


def test_cancel_load_test_requires_active_engine() -> None:
    async def _run() -> None:
        with pytest.raises(PtRunNotRunningError):
            await cancel_load_test(uuid.uuid4())

    asyncio.run(_run())


def test_persist_metric_snapshots_writes_rows(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        run, _ = _seed_run(db)
        recorded_at = datetime.now(timezone.utc)
        snapshots = [
            MetricSnapshot(
                sampler_key="sampler-001",
                recorded_at=recorded_at,
                qps=10.0,
                avg_rt_ms=45.0,
                rt_p95_ms=80.0,
                rt_p99_ms=95.0,
                error_rate_percent=2.5,
            ),
            MetricSnapshot(
                sampler_key="__aggregate__",
                recorded_at=recorded_at,
                qps=10.0,
                avg_rt_ms=45.0,
                rt_p95_ms=80.0,
                rt_p99_ms=95.0,
                error_rate_percent=2.5,
            ),
        ]

        persist_metric_snapshots(run.id, snapshots)

        count = db.scalar(
            select(func.count())
            .select_from(PtRunMetricPoint)
            .where(PtRunMetricPoint.pt_run_id == run.id)
        )
        assert count == 2
        saved = db.scalars(
            select(PtRunMetricPoint)
            .where(PtRunMetricPoint.pt_run_id == run.id)
            .order_by(PtRunMetricPoint.sampler_key)
        ).all()
        assert saved[0].sampler_key == "__aggregate__"
        assert saved[0].qps == 10.0
        assert saved[1].sampler_key == "sampler-001"
    finally:
        db.close()
        engine.dispose()


def test_start_load_test_persists_final_metric_flush(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id

        async def fake_run() -> None:
            aggregator = pt_run_orchestrator._active_aggregators.get(run_id)
            assert aggregator is not None
            aggregator.record(
                LoadSampleResult(
                    sampler_key="sampler-001",
                    sampler_name="List Users",
                    status_code=200,
                    response_time_ms=120.0,
                    success=True,
                    error_type=None,
                    message=None,
                    occurred_at=datetime.now(timezone.utc),
                )
            )

        async def _run() -> None:
            with patch("app.services.pt_run_orchestrator.PtLoadEngine") as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = AsyncMock(side_effect=fake_run)
                mock_engine.stop_reason = PtRunStopReason.DURATION_REACHED.value
                await start_load_test(run_id)

        asyncio.run(_run())

        count = db.scalar(
            select(func.count())
            .select_from(PtRunMetricPoint)
            .where(PtRunMetricPoint.pt_run_id == run_id)
        )
        assert count == 2
        sampler_point = db.scalar(
            select(PtRunMetricPoint).where(
                PtRunMetricPoint.pt_run_id == run_id,
                PtRunMetricPoint.sampler_key == "sampler-001",
            )
        )
        assert sampler_point is not None
        assert sampler_point.avg_rt_ms == 120.0

        db.expire_all()
        saved = db.get(PtRun, run_id)
        assert saved is not None
        assert saved.summary_json is not None
        assert saved.summary_json["status"] == PtRunStatus.COMPLETED.value
        assert saved.summary_json["stop_reason"] == PtRunStopReason.DURATION_REACHED.value
        assert len(saved.summary_json["interfaces"]) == 1
        interface = saved.summary_json["interfaces"][0]
        assert interface["sampler_key"] == "sampler-001"
        assert interface["name"] == "List Users"
        assert interface["total_requests"] == 1
        assert interface["rt_p95_ms"] == 120.0
        assert interface["rt_p99_ms"] == 120.0
    finally:
        db.close()
        engine.dispose()


def test_start_load_test_cancelled_run_persists_summary_json(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id

        async def fake_run() -> None:
            aggregator = pt_run_orchestrator._active_aggregators.get(run_id)
            assert aggregator is not None
            aggregator.record(
                LoadSampleResult(
                    sampler_key="sampler-001",
                    sampler_name="List Users",
                    status_code=500,
                    response_time_ms=80.0,
                    success=False,
                    error_type="http_error",
                    message="HTTP 500",
                    occurred_at=datetime.now(timezone.utc),
                )
            )

        async def _run() -> None:
            with patch("app.services.pt_run_orchestrator.PtLoadEngine") as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = AsyncMock(side_effect=fake_run)
                mock_engine.stop_reason = PtRunStopReason.MANUAL_CANCEL.value
                await start_load_test(run_id)

        asyncio.run(_run())

        db.expire_all()
        saved = db.get(PtRun, run_id)
        assert saved is not None
        assert saved.status == PtRunStatus.CANCELLED.value
        assert saved.summary_json is not None
        assert saved.summary_json["status"] == PtRunStatus.CANCELLED.value
        assert saved.summary_json["stop_reason"] == PtRunStopReason.MANUAL_CANCEL.value
        assert saved.summary_json["interfaces"][0]["failed_requests"] == 1
    finally:
        db.close()
        engine.dispose()


def test_start_load_test_failed_run_skips_summary_json(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id

        async def _run() -> None:
            with patch("app.services.pt_run_orchestrator.PtLoadEngine") as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = AsyncMock(side_effect=RuntimeError("engine boom"))
                await start_load_test(run_id)

        asyncio.run(_run())

        db.expire_all()
        saved = db.get(PtRun, run_id)
        assert saved is not None
        assert saved.status == PtRunStatus.FAILED.value
        assert saved.summary_json is None
        assert saved.error_message == "engine boom"
    finally:
        db.close()
        engine.dispose()


def test_persist_error_log_sanitizes_message(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        run, _ = _seed_run(db)
        persist_error_log(
            run.id,
            LoadSampleResult(
                sampler_key="sampler-001",
                sampler_name="List Users",
                status_code=401,
                response_time_ms=50.0,
                success=False,
                error_type="http_error",
                message="Authorization: Bearer leaked-token",
                occurred_at=datetime.now(timezone.utc),
            ),
        )

        saved = db.scalar(
            select(PtRunErrorLog).where(PtRunErrorLog.pt_run_id == run.id)
        )
        assert saved is not None
        assert saved.message == "Authorization: ***"
    finally:
        db.close()
        engine.dispose()


def test_start_load_test_persists_sanitized_error_logs(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id

        async def fake_run() -> None:
            aggregator = pt_run_orchestrator._active_aggregators.get(run_id)
            assert aggregator is not None
            recorder = pt_run_orchestrator._build_sample_recorder(run_id, aggregator)
            recorder(
                LoadSampleResult(
                    sampler_key="sampler-001",
                    sampler_name="List Users",
                    status_code=401,
                    response_time_ms=80.0,
                    success=False,
                    error_type="http_error",
                    message="Authorization: Bearer leaked-token",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
            flush_sampled_error_logs(run_id)

        async def _run() -> None:
            with patch("app.services.pt_run_orchestrator.PtLoadEngine") as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = AsyncMock(side_effect=fake_run)
                mock_engine.stop_reason = PtRunStopReason.DURATION_REACHED.value
                await start_load_test(run_id)

        asyncio.run(_run())

        saved = db.scalar(
            select(PtRunErrorLog).where(PtRunErrorLog.pt_run_id == run_id)
        )
        assert saved is not None
        assert saved.message == "Authorization: ***"
    finally:
        db.close()
        engine.dispose()


def test_flush_loop_persists_metrics_while_buffering_errors(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = _session(migrated_db)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pt_run_orchestrator.database, "SessionLocal", session_factory)
    try:
        run, _ = _seed_run(db)
        run_id = run.id
        aggregator = PtMetricsAggregator(flush_interval_seconds=1)
        pt_run_orchestrator._run_sidecars[run_id] = pt_run_orchestrator._RunTelemetrySidecar()
        recorder = pt_run_orchestrator._build_sample_recorder(run_id, aggregator)

        for index in range(200):
            recorder(
                LoadSampleResult(
                    sampler_key="sampler-001",
                    sampler_name="List Users",
                    status_code=None,
                    response_time_ms=1.0,
                    success=False,
                    error_type="connection_error",
                    message=f"connection failed #{index}",
                    occurred_at=datetime.now(timezone.utc),
                )
            )

        snapshots = aggregator.build_flush_snapshots(datetime.now(timezone.utc))
        pt_run_orchestrator.persist_metric_snapshots(run_id, snapshots)
        flush_sampled_error_logs(run_id)

        metric_count = db.scalar(
            select(func.count())
            .select_from(PtRunMetricPoint)
            .where(PtRunMetricPoint.pt_run_id == run_id)
        )
        error_count = db.scalar(
            select(func.count())
            .select_from(PtRunErrorLog)
            .where(PtRunErrorLog.pt_run_id == run_id)
        )
        assert metric_count == 2
        assert error_count == 5
    finally:
        db.close()
        engine.dispose()

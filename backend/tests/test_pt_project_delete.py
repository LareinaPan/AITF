import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.pt_project import PtProject
from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.models.user import User
from app.services.pt_project_delete_service import (
    PtProjectRunningError,
    delete_pt_project,
)


def _session(migrated_db: str) -> tuple[Session, object]:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_factory(), engine


def _seed_project_with_run(db: Session, *, status: str = PtRunStatus.COMPLETED.value) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        username=f"delete_user_{uuid.uuid4().hex[:8]}",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    project_id = uuid.uuid4()
    db.add(
        PtProject(
            id=project_id,
            name="Delete Test Project",
            created_by=user.id,
        )
    )
    db.flush()

    scenario_id = uuid.uuid4()
    db.add(
        PtScenario(
            id=scenario_id,
            pt_project_id=project_id,
            name="Delete Test Scenario",
        )
    )
    db.flush()

    db.add(PtScript(pt_scenario_id=scenario_id))
    db.flush()

    run_id = uuid.uuid4()
    db.add(
        PtRun(
            id=run_id,
            pt_project_id=project_id,
            pt_scenario_id=scenario_id,
            scenario_name_snapshot="Delete Test Scenario",
            status=status,
            config_snapshot_json={"max_concurrency": 1, "ramp_up_seconds": 0, "stop_mode": "duration"},
            triggered_by=user.id,
        )
    )
    db.flush()

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            PtRunMetricPoint(
                pt_run_id=run_id,
                sampler_key="GET /posts",
                recorded_at=now,
                qps=10.0,
                avg_rt_ms=50.0,
            )
            for _ in range(50)
        ]
    )
    db.add_all(
        [
            PtRunErrorLog(
                pt_run_id=run_id,
                sampler_key="GET /posts",
                sampler_name="GET /posts",
                error_type="http_error",
                message=f"sample error {index}",
            )
            for index in range(500)
        ]
    )
    db.commit()
    return project_id


def test_delete_pt_project_bulk_removes_related_rows(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id = _seed_project_with_run(db)

        delete_pt_project(db, project_id)

        assert db.get(PtProject, project_id) is None
        assert db.scalar(select(func.count()).select_from(PtRun)) == 0
        assert db.scalar(select(func.count()).select_from(PtRunErrorLog)) == 0
        assert db.scalar(select(func.count()).select_from(PtRunMetricPoint)) == 0
    finally:
        db.close()
        engine.dispose()


def test_delete_pt_project_rejects_running_load_test(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id = _seed_project_with_run(db, status=PtRunStatus.RUNNING.value)

        with pytest.raises(PtProjectRunningError):
            delete_pt_project(db, project_id)

        assert db.get(PtProject, project_id) is not None
    finally:
        db.close()
        engine.dispose()


def test_delete_pt_project_api_with_heavy_run_history(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    db, engine = _session(migrated_db)
    try:
        project_id = _seed_project_with_run(db)
    finally:
        db.close()
        engine.dispose()

    response = client.delete(
        f"/api/v1/pt-projects/{project_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    missing_response = client.get(
        f"/api/v1/pt-projects/{project_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.pt_project import PtProject
from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript
from app.models.user import User
from app.services.pt_run_orchestrator import build_config_snapshot_from_script
from app.services.pt_run_recovery_service import (
    ORPHAN_ERROR_MESSAGE,
    recover_orphaned_running_runs,
)


def _session(migrated_db: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_factory(), engine


def _seed_running_run(db: Session) -> PtRun:
    user = User(
        id=uuid.uuid4(),
        username=f"recover_user_{uuid.uuid4().hex[:8]}",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    project = PtProject(id=uuid.uuid4(), name="Recover Project", created_by=user.id)
    db.add(project)
    db.flush()

    scenario = PtScenario(
        id=uuid.uuid4(),
        pt_project_id=project.id,
        name="Recover Scenario",
    )
    db.add(scenario)
    db.flush()

    script = PtScript(
        pt_scenario_id=scenario.id,
        parsed_plan_json={"samplers": [], "thread_groups": [], "parse_warnings": []},
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
    return run


def test_recover_orphaned_running_runs_marks_failed(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        run = _seed_running_run(db)
        recovered = recover_orphaned_running_runs(db)
        assert recovered == 1

        db.expire_all()
        saved = db.get(PtRun, run.id)
        assert saved is not None
        assert saved.status == PtRunStatus.FAILED.value
        assert saved.stop_reason == PtRunStopReason.ENGINE_ERROR.value
        assert saved.error_message == ORPHAN_ERROR_MESSAGE
        assert saved.ended_at is not None
    finally:
        db.close()
        engine.dispose()


def test_recover_orphaned_running_runs_noop_when_none_running(migrated_db: str) -> None:
    db, engine = _session(migrated_db)
    try:
        assert recover_orphaned_running_runs(db) == 0
    finally:
        db.close()
        engine.dispose()

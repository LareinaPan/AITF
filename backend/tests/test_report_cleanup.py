import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.test_plan import PlanRun, TestPlan
from app.services.report_cleanup_service import cleanup_expired_plan_runs


def _create_plan_run(session) -> tuple[TestPlan, PlanRun]:
    from app.models.environment import Environment
    from app.models.project import Project
    from app.models.user import User

    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()

    project = Project(name="Cleanup Project", created_by=user.id)
    environment = Environment(name=f"env_{uuid.uuid4().hex[:8]}", is_default=False)
    session.add_all([project, environment])
    session.flush()

    plan = TestPlan(
        project_id=project.id,
        name="Cleanup Plan",
        environment_id=environment.id,
    )
    session.add(plan)
    session.flush()

    plan_run = PlanRun(plan_id=plan.id, status="completed")
    session.add(plan_run)
    session.commit()
    session.refresh(plan_run)
    return plan, plan_run


def _set_created_at(session, plan_run: PlanRun, created_at: datetime) -> None:
    plan_run.created_at = created_at
    session.commit()


def _create_artifact_dirs(tmp_path: Path, run_id: uuid.UUID) -> None:
    results_dir = tmp_path / "results" / str(run_id)
    reports_dir = tmp_path / "reports" / str(run_id)
    results_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (results_dir / "sample-result.json").write_text("{}", encoding="utf-8")
    (reports_dir / "index.html").write_text("<html></html>", encoding="utf-8")


def test_cleanup_deletes_expired_runs_and_artifact_dirs(
    migrated_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        _, expired_run = _create_plan_run(session)
        _create_artifact_dirs(tmp_path, expired_run.id)
        _set_created_at(
            session,
            expired_run,
            datetime.now(timezone.utc) - timedelta(days=31),
        )

        summary = cleanup_expired_plan_runs(session, retention_days=30)

        assert summary.deleted_runs == 1
        assert summary.deleted_directories == 2
        assert session.get(PlanRun, expired_run.id) is None
        assert not (tmp_path / "results" / str(expired_run.id)).exists()
        assert not (tmp_path / "reports" / str(expired_run.id)).exists()

    engine.dispose()


def test_cleanup_preserves_recent_runs(
    migrated_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        _, recent_run = _create_plan_run(session)
        _create_artifact_dirs(tmp_path, recent_run.id)
        _set_created_at(
            session,
            recent_run,
            datetime.now(timezone.utc) - timedelta(days=10),
        )

        summary = cleanup_expired_plan_runs(session, retention_days=30)

        assert summary.deleted_runs == 0
        assert summary.deleted_directories == 0
        assert session.get(PlanRun, recent_run.id) is not None
        assert (tmp_path / "results" / str(recent_run.id)).exists()
        assert (tmp_path / "reports" / str(recent_run.id)).exists()

    engine.dispose()


def test_cleanup_only_removes_expired_runs(
    migrated_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")

    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)

    with session_factory() as session:
        _, expired_run = _create_plan_run(session)
        _, recent_run = _create_plan_run(session)
        _set_created_at(session, expired_run, now - timedelta(days=40))
        _set_created_at(session, recent_run, now - timedelta(days=5))

        summary = cleanup_expired_plan_runs(session, retention_days=30, now=now)

        assert summary.deleted_runs == 1
        remaining_ids = set(session.scalars(select(PlanRun.id)).all())
        assert recent_run.id in remaining_ids
        assert expired_run.id not in remaining_ids

    engine.dispose()

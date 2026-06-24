import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.environment import Environment, EnvironmentVariable
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, PlanRun, TestPlan
from app.models.user import User
from app.services.plan_execution_service import execute_test_plan
from app.services.test_runner import (
    HttpResponseSnapshot,
    PlanRunCaseResult,
    PlanRunResult,
    PreparedRequest,
    SingleRunResult,
)


def _create_session(migrated_db: str):
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine, session_factory


def _seed_plan(session) -> uuid.UUID:
    user = User(username=f"exec_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()

    project = Project(
        name="Exec Project",
        created_by=user.id,
        feishu_webhook_url="https://example.com/hook",
    )
    session.add(project)
    session.flush()

    environment = Environment(name=f"env_{uuid.uuid4().hex[:6]}", is_default=False)
    session.add(environment)
    session.flush()
    session.add(
        EnvironmentVariable(
            environment_id=environment.id,
            key="base_url",
            value="http://localhost:8080",
            is_secret=False,
        )
    )

    test_case = TestCase(
        project_id=project.id,
        name="Case 1",
        request_json={
            "method": "GET",
            "url": "{{base_url}}/api",
            "headers": [],
            "query": [],
            "body": {"type": "none", "content": ""},
        },
    )
    session.add(test_case)
    session.flush()

    plan = TestPlan(
        project_id=project.id,
        name="Exec Plan",
        environment_id=environment.id,
    )
    session.add(plan)
    session.flush()
    session.add(PlanCase(plan_id=plan.id, case_id=test_case.id, sort_order=0))
    session.commit()
    return plan.id


@patch("app.services.plan_execution_service.notify_plan_run_completed")
@patch("app.services.plan_execution_service.generate_allure_report")
@patch("app.services.plan_execution_service.AllureReportWriter")
@patch("app.services.plan_execution_service.TestRunner")
def test_execute_test_plan_persists_plan_run(
    mock_runner_cls: MagicMock,
    mock_writer_cls: MagicMock,
    mock_generate: MagicMock,
    mock_notify: MagicMock,
    migrated_db: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setenv("REPORT_BASE_URL", "http://localhost:8000/reports")

    from app.config import get_settings

    get_settings.cache_clear()

    case_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    env_id = uuid.uuid4()
    single = SingleRunResult(
        case_id=case_id,
        case_name="Case 1",
        environment_id=env_id,
        environment_name="dev",
        prepared_request=PreparedRequest(
            method="GET",
            url="http://localhost/api",
            headers={},
            params={},
            body_type="none",
            body_content="",
        ),
        assertions_json={"status_code": 200, "max_response_time_ms": 3000, "body_rules": []},
        passed=True,
        response=HttpResponseSnapshot(status_code=200, body="ok", elapsed_ms=1.0),
        assertions=None,
        error=None,
    )
    mock_runner_cls.return_value.run_plan.return_value = PlanRunResult(
        plan_id=plan_id,
        plan_name="Exec Plan",
        environment_id=env_id,
        environment_name="dev",
        trigger="manual",
        total_count=1,
        pass_count=1,
        fail_count=0,
        passed=True,
        case_results=[
            PlanRunCaseResult(
                case_id=case_id,
                case_name="Case 1",
                sort_order=0,
                passed=True,
                result=single,
            )
        ],
    )
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_generate.return_value = tmp_path / "reports" / "run"

    engine, session_factory = _create_session(migrated_db)
    with session_factory() as session:
        real_plan_id = _seed_plan(session)
        plan_run, _ = execute_test_plan(session, real_plan_id, trigger="manual")

        saved = session.get(PlanRun, plan_run.id)
        assert saved is not None
        assert saved.status == "completed"
        assert saved.total_count == 1
        assert saved.pass_count == 1
        assert saved.fail_count == 0
        assert saved.allure_report_url is not None
        assert saved.allure_report_url.startswith("http://localhost:8000/reports/")

    mock_notify.assert_called_once()
    engine.dispose()
    get_settings.cache_clear()


@patch("app.services.plan_execution_service.notify_plan_run_completed")
@patch("app.services.plan_execution_service.generate_allure_report")
@patch("app.services.plan_execution_service.AllureReportWriter")
@patch("app.services.plan_execution_service.TestRunner")
def test_execute_test_plan_skips_notify_when_disabled(
    mock_runner_cls: MagicMock,
    mock_writer_cls: MagicMock,
    mock_generate: MagicMock,
    mock_notify: MagicMock,
    migrated_db: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setenv("REPORT_BASE_URL", "http://localhost:8000/reports")

    from app.config import get_settings

    get_settings.cache_clear()

    case_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    env_id = uuid.uuid4()
    single = SingleRunResult(
        case_id=case_id,
        case_name="Case 1",
        environment_id=env_id,
        environment_name="dev",
        prepared_request=PreparedRequest(
            method="GET",
            url="http://localhost/api",
            headers={},
            params={},
            body_type="none",
            body_content="",
        ),
        assertions_json={"status_code": 200, "max_response_time_ms": 3000, "body_rules": []},
        passed=True,
        response=HttpResponseSnapshot(status_code=200, body="ok", elapsed_ms=1.0),
        assertions=None,
        error=None,
    )
    mock_runner_cls.return_value.run_plan.return_value = PlanRunResult(
        plan_id=plan_id,
        plan_name="Exec Plan",
        environment_id=env_id,
        environment_name="dev",
        trigger="manual",
        total_count=1,
        pass_count=1,
        fail_count=0,
        passed=True,
        case_results=[
            PlanRunCaseResult(
                case_id=case_id,
                case_name="Case 1",
                sort_order=0,
                passed=True,
                result=single,
            )
        ],
    )
    mock_writer_cls.return_value = MagicMock()
    mock_generate.return_value = tmp_path / "reports" / "run"

    engine, session_factory = _create_session(migrated_db)
    with session_factory() as session:
        real_plan_id = _seed_plan(session)
        plan = session.get(TestPlan, real_plan_id)
        assert plan is not None
        plan.notify_on_complete = False
        session.commit()

        execute_test_plan(session, real_plan_id, trigger="manual")

    mock_notify.assert_not_called()
    engine.dispose()
    get_settings.cache_clear()

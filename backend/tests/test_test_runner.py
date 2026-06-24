import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.models.environment import Environment, EnvironmentVariable
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, TestPlan
from app.models.user import User
from app.services.test_runner import (
    EnvironmentNotFoundError,
    HttpResponseSnapshot,
    PlanRunResult,
    RequestBuildError,
    TestCaseNotFoundError,
    TestPlanNotFoundError,
    TestRunner,
    build_httpx_request_kwargs,
    execute_http_request,
    prepare_request,
)
from app.services.variable_resolver import MissingVariableError


def _create_session(migrated_db: str):
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine, session_factory


def _seed_case_and_environment(
    session,
    *,
    assertions_json: dict | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(username=f"runner_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()

    project = Project(name="Runner Project", created_by=user.id)
    session.add(project)
    session.flush()

    environment = Environment(name=f"dev_{uuid.uuid4().hex[:6]}", is_default=False)
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
        name="Get users",
        request_json={
            "method": "GET",
            "url": "{{base_url}}/api/users",
            "headers": [{"key": "Authorization", "value": "Bearer test-token"}],
            "query": [{"key": "page", "value": "1"}],
            "body": {"type": "none", "content": ""},
        },
        assertions_json=assertions_json
        or {
            "status_code": 200,
            "max_response_time_ms": 3000,
            "body_rules": [{"type": "contains", "value": "success"}],
        },
    )
    session.add(test_case)
    session.commit()
    return test_case.id, environment.id


def _seed_plan_with_cases(
    session,
    *,
    case_specs: list[dict] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    user = User(username=f"plan_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()

    project = Project(name="Plan Runner Project", created_by=user.id)
    session.add(project)
    session.flush()

    environment = Environment(name=f"plan_env_{uuid.uuid4().hex[:6]}", is_default=False)
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

    specs = case_specs or [
        {"name": "Case A", "assertions_json": {"status_code": 200, "max_response_time_ms": 3000, "body_rules": []}},
        {"name": "Case B", "assertions_json": {"status_code": 200, "max_response_time_ms": 3000, "body_rules": []}},
    ]

    case_ids: list[uuid.UUID] = []
    for index, spec in enumerate(specs):
        test_case = TestCase(
            project_id=project.id,
            name=spec["name"],
            request_json={
                "method": "GET",
                "url": "{{base_url}}/api/items",
                "headers": [],
                "query": [],
                "body": {"type": "none", "content": ""},
            },
            assertions_json=spec.get("assertions_json")
            or {
                "status_code": 200,
                "max_response_time_ms": 3000,
                "body_rules": [],
            },
        )
        session.add(test_case)
        session.flush()
        case_ids.append(test_case.id)

    plan = TestPlan(
        project_id=project.id,
        name="Regression Plan",
        environment_id=environment.id,
    )
    session.add(plan)
    session.flush()

    for sort_order, case_id in enumerate(case_ids):
        session.add(PlanCase(plan_id=plan.id, case_id=case_id, sort_order=sort_order))

    session.commit()
    return plan.id, environment.id, case_ids


def test_prepare_request_resolves_variables() -> None:
    request_json = {
        "method": "post",
        "url": "{{base_url}}/api/login",
        "headers": [{"key": "Content-Type", "value": "application/json"}],
        "query": [{"key": "retry", "value": "{{max_retry}}"}],
        "body": {"type": "json", "content": '{"username":"{{user}}"}'},
    }
    variables = {
        "base_url": "http://localhost:8080",
        "max_retry": "3",
        "user": "demo",
    }

    prepared = prepare_request(request_json, variables)

    assert prepared.method == "POST"
    assert prepared.url == "http://localhost:8080/api/login"
    assert prepared.headers == {"Content-Type": "application/json"}
    assert prepared.params == {"retry": "3"}
    assert prepared.body_type == "json"
    assert prepared.body_content == '{"username":"demo"}'


def test_prepare_request_missing_variable_raises() -> None:
    with pytest.raises(MissingVariableError):
        prepare_request({"method": "GET", "url": "{{base_url}}/api"}, {})


def test_prepare_request_uses_exact_environment_values() -> None:
    prepared = prepare_request(
        {
            "method": "GET",
            "url": "{{base_url}}/api/requirements/",
            "headers": [{"key": "Authorization", "value": "Bearer {{token}}"}],
            "query": [{"key": "page", "value": "1"}],
            "body": {"type": "none", "content": ""},
        },
        {
            "base_url": "http://127.0.0.1:8001",
            "token": "real-token",
        },
    )
    assert prepared.url == "http://127.0.0.1:8001/api/requirements/"
    assert prepared.headers["Authorization"] == "Bearer real-token"
    assert prepared.params == {"page": "1"}


def test_prepare_request_rewrites_loopback_after_variable_substitution() -> None:
    prepared = prepare_request(
        {
            "method": "GET",
            "url": "{{base_url}}/api/requirements/",
            "headers": [],
            "query": [],
            "body": {"type": "none", "content": ""},
        },
        {"base_url": "http://127.0.0.1:8001"},
        host_alias="host.docker.internal",
    )
    assert prepared.url == "http://host.docker.internal:8001/api/requirements/"


def test_format_http_error_connection_refused_includes_hint() -> None:
    from app.services.test_runner import format_http_error

    message = format_http_error(
        httpx.ConnectError("[Errno 111] Connection refused"),
        host_alias="host.docker.internal",
    )
    assert "Connection refused" in message
    assert "host.docker.internal" in message


def test_validate_authorization_header_rejects_url_token() -> None:
    from app.services.test_runner import validate_authorization_header

    error = validate_authorization_header(
        {
            "authorization": (
                "bearer http://localhost:5174/projects/abc/cases/def"
            ),
        }
    )
    assert error is not None
    assert "URL" in error


def test_build_httpx_request_kwargs_json_body() -> None:
    from app.services.test_runner import validate_authorization_header

    error = validate_authorization_header(
        {
            "authorization": (
                "bearer http://localhost:5174/projects/abc/cases/def"
            ),
        }
    )
    assert error is not None
    assert "URL" in error


def test_build_httpx_request_kwargs_json_body() -> None:
    prepared = prepare_request(
        {
            "method": "POST",
            "url": "http://localhost/api",
            "headers": [],
            "query": [],
            "body": {"type": "json", "content": '{"name":"demo"}'},
        },
        {},
    )

    kwargs = build_httpx_request_kwargs(prepared)

    assert kwargs["json"] == {"name": "demo"}


def test_build_httpx_request_kwargs_invalid_json_raises() -> None:
    prepared = prepare_request(
        {
            "method": "POST",
            "url": "http://localhost/api",
            "headers": [],
            "query": [],
            "body": {"type": "json", "content": "not-json"},
        },
        {},
    )

    with pytest.raises(RequestBuildError):
        build_httpx_request_kwargs(prepared)


def test_execute_http_request_uses_client(migrated_db: str) -> None:
    prepared = prepare_request(
        {"method": "GET", "url": "http://example.com", "headers": [], "query": [], "body": {"type": "none", "content": ""}},
        {},
    )
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok":true}'
    mock_client.request.return_value = mock_response

    snapshot = execute_http_request(prepared, client=mock_client)

    assert snapshot.status_code == 200
    assert snapshot.body == '{"ok":true}'
    assert snapshot.elapsed_ms >= 0
    mock_client.request.assert_called_once()


@patch("app.services.test_runner.execute_http_request")
def test_run_single_executes_request_and_passes_assertions(
    mock_execute: MagicMock,
    migrated_db: str,
) -> None:
    mock_execute.return_value = HttpResponseSnapshot(
        status_code=200,
        body='{"code":"0","message":"success"}',
        elapsed_ms=120.5,
    )

    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        case_id, env_id = _seed_case_and_environment(session)
        session.commit()

        result = TestRunner(session).run_single(case_id, env_id)

        assert result.passed is True
        assert result.error is None
        assert result.response is not None
        assert result.response.status_code == 200
        assert result.assertions is not None
        assert result.assertions.passed is True
        assert result.prepared_request.url == "http://localhost:8080/api/users"
        assert result.prepared_request.headers["Authorization"] == "Bearer test-token"
        mock_execute.assert_called_once()


@patch("app.services.test_runner.execute_http_request")
def test_run_single_fails_when_assertions_not_met(
    mock_execute: MagicMock,
    migrated_db: str,
) -> None:
    mock_execute.return_value = HttpResponseSnapshot(
        status_code=500,
        body='{"error":"failed"}',
        elapsed_ms=4000.0,
    )

    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        case_id, env_id = _seed_case_and_environment(session)
        result = TestRunner(session).run_single(case_id, env_id)

        assert result.passed is False
        assert result.assertions is not None
        assert result.assertions.passed is False
        failed = [check for check in result.assertions.checks if not check.passed]
        assert len(failed) >= 2


@patch("app.services.test_runner.execute_http_request")
def test_run_single_handles_http_error(mock_execute: MagicMock, migrated_db: str) -> None:
    mock_execute.side_effect = httpx.ConnectError("connection refused")

    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        case_id, env_id = _seed_case_and_environment(session)
        result = TestRunner(session).run_single(case_id, env_id)

        assert result.passed is False
        assert result.response is None
        assert result.assertions is None
        assert result.error is not None
        assert "connection refused" in result.error

    engine.dispose()


def test_run_single_missing_case(migrated_db: str) -> None:
    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        _, env_id = _seed_case_and_environment(session)
        runner = TestRunner(session)

        with pytest.raises(TestCaseNotFoundError):
            runner.run_single(uuid.uuid4(), env_id)

    engine.dispose()


def test_run_single_missing_environment(migrated_db: str) -> None:
    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        case_id, _ = _seed_case_and_environment(session)
        runner = TestRunner(session)

        with pytest.raises(EnvironmentNotFoundError):
            runner.run_single(case_id, uuid.uuid4())

    engine.dispose()


def test_run_single_missing_variable_returns_error_result(migrated_db: str) -> None:
    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        user = User(username=f"runner_{uuid.uuid4().hex[:8]}", password_hash="hash")
        session.add(user)
        session.flush()

        project = Project(name="Missing Var Project", created_by=user.id)
        session.add(project)
        session.flush()

        environment = Environment(name=f"empty_{uuid.uuid4().hex[:6]}", is_default=False)
        session.add(environment)
        session.flush()

        test_case = TestCase(
            project_id=project.id,
            name="Needs token",
            request_json={
                "method": "GET",
                "url": "{{base_url}}/api",
                "headers": [{"key": "Authorization", "value": "Bearer {{token}}"}],
                "query": [],
                "body": {"type": "none", "content": ""},
            },
        )
        session.add(test_case)
        session.commit()

        result = TestRunner(session).run_single(test_case.id, environment.id)

        assert result.passed is False
        assert result.error is not None
        assert "Missing environment variable" in result.error
        assert result.response is None

    engine.dispose()


@patch("app.services.test_runner.execute_http_request")
def test_run_plan_executes_cases_in_sort_order(
    mock_execute: MagicMock,
    migrated_db: str,
) -> None:
    mock_execute.return_value = HttpResponseSnapshot(
        status_code=200,
        body="ok",
        elapsed_ms=50.0,
    )

    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        plan_id, environment_id, case_ids = _seed_plan_with_cases(
            session,
            case_specs=[
                {"name": "First"},
                {"name": "Second"},
                {"name": "Third"},
            ],
        )

        session.execute(
            update(PlanCase)
            .where(PlanCase.plan_id == plan_id, PlanCase.case_id == case_ids[0])
            .values(sort_order=2)
        )
        session.execute(
            update(PlanCase)
            .where(PlanCase.plan_id == plan_id, PlanCase.case_id == case_ids[1])
            .values(sort_order=0)
        )
        session.execute(
            update(PlanCase)
            .where(PlanCase.plan_id == plan_id, PlanCase.case_id == case_ids[2])
            .values(sort_order=1)
        )
        session.commit()

        result = TestRunner(session).run_plan(plan_id)

        assert isinstance(result, PlanRunResult)
        assert result.total_count == 3
        assert result.pass_count == 3
        assert result.fail_count == 0
        assert result.passed is True
        assert result.environment_id == environment_id
        assert [item.case_name for item in result.case_results] == ["Second", "Third", "First"]
        assert mock_execute.call_count == 3

    engine.dispose()


@patch("app.services.test_runner.execute_http_request")
def test_run_plan_continues_after_failure(mock_execute: MagicMock, migrated_db: str) -> None:
    mock_execute.side_effect = [
        HttpResponseSnapshot(status_code=200, body="ok", elapsed_ms=10.0),
        HttpResponseSnapshot(status_code=500, body="error", elapsed_ms=10.0),
        HttpResponseSnapshot(status_code=200, body="ok", elapsed_ms=10.0),
    ]

    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        plan_id, _, _ = _seed_plan_with_cases(
            session,
            case_specs=[
                {"name": "Pass"},
                {"name": "Fail"},
                {"name": "Pass Again"},
            ],
        )

        result = TestRunner(session).run_plan(plan_id, trigger="manual")

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.passed is False
        assert [item.passed for item in result.case_results] == [True, False, True]
        assert mock_execute.call_count == 3

    engine.dispose()


def test_run_plan_empty_plan_returns_zero_counts(migrated_db: str) -> None:
    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        user = User(username=f"empty_{uuid.uuid4().hex[:8]}", password_hash="hash")
        session.add(user)
        session.flush()

        project = Project(name="Empty Plan Project", created_by=user.id)
        session.add(project)
        session.flush()

        environment = Environment(name=f"env_{uuid.uuid4().hex[:6]}", is_default=False)
        session.add(environment)
        session.flush()

        plan = TestPlan(
            project_id=project.id,
            name="Empty Plan",
            environment_id=environment.id,
        )
        session.add(plan)
        session.commit()

        result = TestRunner(session).run_plan(plan.id)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.passed is True
        assert result.case_results == []

    engine.dispose()


def test_run_plan_missing_plan(migrated_db: str) -> None:
    engine, session_factory = _create_session(migrated_db)

    with session_factory() as session:
        with pytest.raises(TestPlanNotFoundError):
            TestRunner(session).run_plan(uuid.uuid4())

    engine.dispose()

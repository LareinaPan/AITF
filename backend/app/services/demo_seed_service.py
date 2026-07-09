"""Seed demo data for local AITF presentations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import PROJECT_ROOT
from app.core.security import hash_password
from app.models.api_endpoint import ApiEndpoint
from app.models.environment import Environment, EnvironmentVariable
from app.models.project import Project
from app.models.pt_project import PtProject
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript, PtScriptParseStatus, PtScriptStopMode
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, TestPlan
from app.models.user import User
from app.services.api_endpoint_service import upsert_parsed_endpoints
from app.services.openapi_parser import parse_openapi_document
from app.services.pt_jmx_parser import parse_jmx_content, save_pt_jmx_upload

DEMO_OPENAPI_PATH = PROJECT_ROOT / "docs" / "demo" / "demo-openapi.json"
DEMO_JMX_PATH = PROJECT_ROOT / "docs" / "demo" / "demo-load-test.jmx"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo123456"
DEMO_PROJECT_NAME = "Demo 商城 API"
DEMO_PT_PROJECT_NAME = "Demo 压测项目"
DEMO_PT_SCENARIO_NAME = "JSONPlaceholder Demo"
DEMO_JMX_FILENAME = "demo-load-test.jmx"
DEMO_ENV_NAME = "dev"


@dataclass(frozen=True)
class SeedDemoSummary:
    user_id: uuid.UUID
    project_id: uuid.UUID
    environment_id: uuid.UUID
    endpoints_created: int
    endpoints_updated: int
    test_cases_created: int
    test_plans_created: int
    pt_project_id: uuid.UUID
    pt_scenarios_created: int
    pt_jmx_seeded: int


def load_demo_openapi_document() -> dict[str, Any]:
    content = DEMO_OPENAPI_PATH.read_text(encoding="utf-8")
    return json.loads(content)


def get_or_create_demo_user(session: Session) -> User:
    user = session.scalar(select(User).where(User.username == DEMO_USERNAME))
    if user is not None:
        return user

    user = User(username=DEMO_USERNAME, password_hash=hash_password(DEMO_PASSWORD))
    session.add(user)
    session.flush()
    return user


def get_or_create_dev_environment(session: Session) -> Environment:
    environment = session.scalar(select(Environment).where(Environment.name == DEMO_ENV_NAME))
    if environment is None:
        environment = Environment(name=DEMO_ENV_NAME, is_default=True)
        session.add(environment)
        session.flush()

    existing_vars = {
        variable.key: variable
        for variable in session.scalars(
            select(EnvironmentVariable).where(EnvironmentVariable.environment_id == environment.id),
        ).all()
    }
    desired_vars = {
        "base_url": "https://jsonplaceholder.typicode.com",
        "token": "demo-token",
    }
    for key, value in desired_vars.items():
        variable = existing_vars.get(key)
        if variable is None:
            session.add(
                EnvironmentVariable(
                    environment_id=environment.id,
                    key=key,
                    value=value,
                    is_secret=key == "token",
                ),
            )
        else:
            variable.value = value
            variable.is_secret = key == "token"

    session.flush()
    return environment


def get_or_create_demo_project(session: Session, user: User) -> Project:
    project = session.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
    if project is not None:
        return project

    project = Project(
        name=DEMO_PROJECT_NAME,
        description="AITF Demo 示例接口项目，含 Swagger、用例与测试计划",
        created_by=user.id,
    )
    session.add(project)
    session.flush()
    return project


def seed_demo_endpoints(session: Session, project_id: uuid.UUID) -> tuple[int, int]:
    document = load_demo_openapi_document()
    parsed = parse_openapi_document(document)
    result = upsert_parsed_endpoints(session, project_id, parsed)
    return result.created, result.updated


def _build_list_users_case(api_endpoint_id: uuid.UUID | None) -> TestCase:
    return TestCase(
        name="获取用户列表",
        description="Demo：GET /users，断言 200 且响应包含 id",
        status="active",
        priority="P0",
        api_endpoint_id=api_endpoint_id,
        request_json={
            "method": "GET",
            "url": "{{base_url}}/users",
            "headers": [{"key": "Accept", "value": "application/json"}],
            "query": [],
            "body": {"type": "none", "content": ""},
        },
        assertions_json={
            "status_code": 200,
            "max_response_time_ms": 5000,
            "body_rules": [{"type": "contains", "value": "\"id\""}],
        },
    )


def _build_get_user_case(api_endpoint_id: uuid.UUID | None) -> TestCase:
    return TestCase(
        name="获取用户详情",
        description="Demo：GET /users/1",
        status="active",
        priority="P1",
        api_endpoint_id=api_endpoint_id,
        request_json={
            "method": "GET",
            "url": "{{base_url}}/users/1",
            "headers": [{"key": "Accept", "value": "application/json"}],
            "query": [],
            "body": {"type": "none", "content": ""},
        },
        assertions_json={
            "status_code": 200,
            "max_response_time_ms": 5000,
            "body_rules": [{"type": "contains", "value": "\"username\""}],
        },
    )


def seed_demo_test_cases(session: Session, project_id: uuid.UUID) -> int:
    existing_names = set(
        session.scalars(
            select(TestCase.name).where(TestCase.project_id == project_id),
        ).all(),
    )
    if {"获取用户列表", "获取用户详情"}.issubset(existing_names):
        return 0

    endpoints = {
        (endpoint.method, endpoint.path): endpoint
        for endpoint in session.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project_id),
        ).all()
    }
    list_users = endpoints.get(("GET", "/users"))
    get_user = endpoints.get(("GET", "/users/{id}"))
    cases = [
        _build_list_users_case(list_users.id if list_users is not None else None),
        _build_get_user_case(get_user.id if get_user is not None else None),
    ]
    created = 0
    for case in cases:
        if case.name in existing_names:
            continue
        case.project_id = project_id
        session.add(case)
        created += 1

    session.flush()
    return created


def seed_demo_test_plan(session: Session, project_id: uuid.UUID, environment_id: uuid.UUID) -> int:
    plan = session.scalar(
        select(TestPlan).where(
            TestPlan.project_id == project_id,
            TestPlan.name == "Demo 冒烟计划",
        ),
    )
    if plan is not None:
        return 0

    active_cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.project_id == project_id, TestCase.status == "active")
            .order_by(TestCase.created_at),
        ).all(),
    )
    if not active_cases:
        return 0

    plan = TestPlan(
        project_id=project_id,
        name="Demo 冒烟计划",
        cron_expression="0 9 * * *",
        environment_id=environment_id,
        is_enabled=False,
        notify_on_complete=True,
    )
    session.add(plan)
    session.flush()

    for index, case in enumerate(active_cases):
        session.add(PlanCase(plan_id=plan.id, case_id=case.id, sort_order=index))

    session.flush()
    return 1


def get_or_create_demo_pt_project(session: Session, user: User) -> PtProject:
    project = session.scalar(select(PtProject).where(PtProject.name == DEMO_PT_PROJECT_NAME))
    if project is not None:
        return project

    project = PtProject(
        name=DEMO_PT_PROJECT_NAME,
        description="AITF Demo 压测项目，含 jsonplaceholder 示例 JMX 与默认压测配置",
        created_by=user.id,
    )
    session.add(project)
    session.flush()
    return project


def _get_demo_pt_scenario(session: Session, project_id: uuid.UUID) -> PtScenario | None:
    return session.scalar(
        select(PtScenario)
        .where(
            PtScenario.pt_project_id == project_id,
            PtScenario.name == DEMO_PT_SCENARIO_NAME,
        )
        .options(selectinload(PtScenario.script)),
    )


def seed_demo_pt_scenario(session: Session, project_id: uuid.UUID) -> int:
    if _get_demo_pt_scenario(session, project_id) is not None:
        return 0

    scenario = PtScenario(
        pt_project_id=project_id,
        name=DEMO_PT_SCENARIO_NAME,
        description="Demo：对 jsonplaceholder.typicode.com 三个 GET/POST 接口发压",
    )
    scenario.script = PtScript(
        parse_status=PtScriptParseStatus.PENDING.value,
        stop_mode=PtScriptStopMode.DURATION.value,
        max_concurrency=10,
        ramp_up_seconds=5,
        duration_seconds=30,
    )
    session.add(scenario)
    session.flush()
    return 1


def seed_demo_pt_jmx(session: Session, project_id: uuid.UUID) -> int:
    scenario = _get_demo_pt_scenario(session, project_id)
    if scenario is None or scenario.script is None:
        return 0

    script = scenario.script
    if (
        script.parse_status == PtScriptParseStatus.SUCCESS.value
        and script.filename == DEMO_JMX_FILENAME
        and script.file_path
    ):
        return 0

    content = DEMO_JMX_PATH.read_bytes()
    parsed_plan = parse_jmx_content(content)
    saved_path, file_size = save_pt_jmx_upload(
        pt_project_id=project_id,
        filename=DEMO_JMX_FILENAME,
        content=content,
    )

    script.filename = DEMO_JMX_FILENAME
    script.file_path = str(saved_path)
    script.file_size = file_size
    script.parse_status = PtScriptParseStatus.SUCCESS.value
    script.parse_error = None
    script.parsed_plan_json = parsed_plan.to_json()
    script.max_concurrency = 10
    script.ramp_up_seconds = 5
    script.stop_mode = PtScriptStopMode.DURATION.value
    script.duration_seconds = 30
    script.uploaded_at = datetime.now(timezone.utc)
    session.flush()
    return 1


def seed_demo_data(session: Session) -> SeedDemoSummary:
    user = get_or_create_demo_user(session)
    environment = get_or_create_dev_environment(session)
    project = get_or_create_demo_project(session, user)
    created, updated = seed_demo_endpoints(session, project.id)
    test_cases_created = seed_demo_test_cases(session, project.id)
    test_plans_created = seed_demo_test_plan(session, project.id, environment.id)
    pt_project = get_or_create_demo_pt_project(session, user)
    pt_scenarios_created = seed_demo_pt_scenario(session, pt_project.id)
    pt_jmx_seeded = seed_demo_pt_jmx(session, pt_project.id)
    session.commit()

    return SeedDemoSummary(
        user_id=user.id,
        project_id=project.id,
        environment_id=environment.id,
        endpoints_created=created,
        endpoints_updated=updated,
        test_cases_created=test_cases_created,
        test_plans_created=test_plans_created,
        pt_project_id=pt_project.id,
        pt_scenarios_created=pt_scenarios_created,
        pt_jmx_seeded=pt_jmx_seeded,
    )

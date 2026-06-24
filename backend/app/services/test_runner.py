import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.environment import Environment, EnvironmentVariable
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, TestPlan
from app.services.assertion_engine import AssertionsEvaluationResult, evaluate_assertions
from app.services.variable_resolver import (
    MissingVariableError,
    build_variable_map,
    resolve_template,
    rewrite_loopback_host,
)

DEFAULT_HTTP_TIMEOUT = 30.0


class TestCaseNotFoundError(LookupError):
    """Raised when the requested test case does not exist."""


class EnvironmentNotFoundError(LookupError):
    """Raised when the requested environment does not exist."""


class TestPlanNotFoundError(LookupError):
    """Raised when the requested test plan does not exist."""


class RequestBuildError(ValueError):
    """Raised when the prepared request cannot be converted for HTTP execution."""


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    body_type: str
    body_content: str


@dataclass(frozen=True)
class HttpResponseSnapshot:
    status_code: int
    body: str
    elapsed_ms: float


@dataclass(frozen=True)
class SingleRunResult:
    case_id: uuid.UUID
    case_name: str
    environment_id: uuid.UUID
    environment_name: str
    prepared_request: PreparedRequest
    assertions_json: dict[str, Any]
    passed: bool
    response: HttpResponseSnapshot | None
    assertions: AssertionsEvaluationResult | None
    error: str | None = None


@dataclass(frozen=True)
class PlanRunCaseResult:
    case_id: uuid.UUID
    case_name: str
    sort_order: int
    passed: bool
    result: SingleRunResult


@dataclass(frozen=True)
class PlanRunResult:
    plan_id: uuid.UUID
    plan_name: str
    environment_id: uuid.UUID
    environment_name: str
    trigger: str
    total_count: int
    pass_count: int
    fail_count: int
    passed: bool
    case_results: list[PlanRunCaseResult]


def validate_authorization_header(headers: dict[str, str]) -> str | None:
    """Detect common misconfiguration where a URL is used as bearer token."""
    for key, value in headers.items():
        if key.lower() != "authorization":
            continue
        token = value.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if token.startswith(("http://", "https://")):
            return (
                "Authorization header contains a URL instead of an access token. "
                "Check the token environment variable or header template."
            )
    return None


def format_http_error(exc: httpx.HTTPError, *, host_alias: str | None) -> str:
    message = f"HTTP request failed: {exc}"
    error_text = str(exc)
    if "Connection refused" in error_text or "Errno 111" in error_text:
        if host_alias:
            return (
                f"{message}. 目标服务连接被拒绝：请确认被测服务已启动。"
                f" Docker 下 base_url 使用 localhost/127.0.0.1 时会映射为 {host_alias}。"
            )
        return (
            f"{message}. 目标服务连接被拒绝：请确认 base_url 对应的服务已启动；"
            " Docker 部署时 base_url 建议使用 http://host.docker.internal:端口。"
        )
    return message


def prepare_request(
    request_json: dict[str, Any],
    variables: dict[str, str],
    *,
    host_alias: str | None = None,
) -> PreparedRequest:
    """Resolve environment variables and build an HTTP request payload."""
    method = str(request_json.get("method", "GET")).upper()
    url = resolve_template(str(request_json.get("url", "")), variables)
    url = rewrite_loopback_host(url, host_alias)

    headers: dict[str, str] = {}
    for item in request_json.get("headers", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        value = resolve_template(str(item.get("value", "")), variables)
        headers[key] = value

    params: dict[str, str] = {}
    for item in request_json.get("query", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        value = resolve_template(str(item.get("value", "")), variables)
        params[key] = value

    body = request_json.get("body", {})
    body_type = "none"
    body_content = ""
    if isinstance(body, dict):
        body_type = str(body.get("type", "none"))
        body_content = resolve_template(str(body.get("content", "")), variables)

    return PreparedRequest(
        method=method,
        url=url,
        headers=headers,
        params=params,
        body_type=body_type,
        body_content=body_content,
    )


def build_httpx_request_kwargs(prepared: PreparedRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "method": prepared.method,
        "url": prepared.url,
        "headers": prepared.headers,
        "params": prepared.params,
    }

    if prepared.body_type == "none":
        return kwargs

    if prepared.body_type == "json":
        if not prepared.body_content.strip():
            kwargs["json"] = {}
            return kwargs
        try:
            kwargs["json"] = json.loads(prepared.body_content)
        except json.JSONDecodeError as exc:
            raise RequestBuildError(f"Invalid JSON request body: {exc}") from exc
        return kwargs

    if prepared.body_type == "raw":
        kwargs["content"] = prepared.body_content
        return kwargs

    if prepared.body_type == "form":
        kwargs["data"] = dict(parse_qsl(prepared.body_content, keep_blank_values=True))
        return kwargs

    raise RequestBuildError(f"Unsupported request body type: {prepared.body_type}")


def execute_http_request(
    prepared: PreparedRequest,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    client: httpx.Client | None = None,
) -> HttpResponseSnapshot:
    """Send the prepared HTTP request and capture response details."""
    kwargs = build_httpx_request_kwargs(prepared)
    start = time.perf_counter()

    if client is None:
        with httpx.Client(timeout=timeout) as owned_client:
            response = owned_client.request(**kwargs)
    else:
        response = client.request(**kwargs)

    elapsed_ms = (time.perf_counter() - start) * 1000
    return HttpResponseSnapshot(
        status_code=response.status_code,
        body=response.text,
        elapsed_ms=elapsed_ms,
    )


class TestRunner:
    __test__ = False
    """Execute test cases against a selected environment."""

    def __init__(self, db: Session, *, http_timeout: float = DEFAULT_HTTP_TIMEOUT) -> None:
        self.db = db
        self.http_timeout = http_timeout
        self.host_alias = get_settings().runner_host_alias

    def run_single(self, case_id: uuid.UUID, env_id: uuid.UUID) -> SingleRunResult:
        test_case = self._load_test_case(case_id)
        environment = self._load_environment(env_id)
        variables = self._build_variable_map(environment.variables)
        assertions_json = dict(test_case.assertions_json)

        try:
            prepared_request = prepare_request(
                test_case.request_json,
                variables,
                host_alias=self.host_alias,
            )
        except MissingVariableError as exc:
            return SingleRunResult(
                case_id=test_case.id,
                case_name=test_case.name,
                environment_id=environment.id,
                environment_name=environment.name,
                prepared_request=PreparedRequest(
                    method=str(test_case.request_json.get("method", "GET")).upper(),
                    url=str(test_case.request_json.get("url", "")),
                    headers={},
                    params={},
                    body_type="none",
                    body_content="",
                ),
                assertions_json=assertions_json,
                passed=False,
                response=None,
                assertions=None,
                error=str(exc),
            )

        base_result = {
            "case_id": test_case.id,
            "case_name": test_case.name,
            "environment_id": environment.id,
            "environment_name": environment.name,
            "prepared_request": prepared_request,
            "assertions_json": assertions_json,
        }

        auth_error = validate_authorization_header(prepared_request.headers)
        if auth_error is not None:
            return SingleRunResult(
                **base_result,
                passed=False,
                response=None,
                assertions=None,
                error=auth_error,
            )

        try:
            response = execute_http_request(
                prepared_request,
                timeout=self.http_timeout,
            )
        except RequestBuildError as exc:
            return SingleRunResult(
                **base_result,
                passed=False,
                response=None,
                assertions=None,
                error=str(exc),
            )
        except httpx.HTTPError as exc:
            return SingleRunResult(
                **base_result,
                passed=False,
                response=None,
                assertions=None,
                error=format_http_error(exc, host_alias=self.host_alias),
            )

        assertions = evaluate_assertions(
            assertions_json,
            response_status_code=response.status_code,
            response_body=response.body,
            elapsed_ms=response.elapsed_ms,
        )

        return SingleRunResult(
            **base_result,
            passed=assertions.passed,
            response=response,
            assertions=assertions,
            error=None,
        )

    def run_plan(self, plan_id: uuid.UUID, *, trigger: str = "manual") -> PlanRunResult:
        plan = self._load_test_plan(plan_id)
        ordered_plan_cases = sorted(plan.plan_cases, key=lambda item: item.sort_order)
        case_results: list[PlanRunCaseResult] = []

        for plan_case in ordered_plan_cases:
            single_result = self.run_single(plan_case.case_id, plan.environment_id)
            case_results.append(
                PlanRunCaseResult(
                    case_id=single_result.case_id,
                    case_name=single_result.case_name,
                    sort_order=plan_case.sort_order,
                    passed=single_result.passed,
                    result=single_result,
                )
            )

        pass_count = sum(1 for item in case_results if item.passed)
        fail_count = len(case_results) - pass_count

        return PlanRunResult(
            plan_id=plan.id,
            plan_name=plan.name,
            environment_id=plan.environment_id,
            environment_name=plan.environment.name,
            trigger=trigger,
            total_count=len(case_results),
            pass_count=pass_count,
            fail_count=fail_count,
            passed=fail_count == 0,
            case_results=case_results,
        )

    def _load_test_plan(self, plan_id: uuid.UUID) -> TestPlan:
        plan = self.db.scalar(
            select(TestPlan)
            .where(TestPlan.id == plan_id)
            .options(
                selectinload(TestPlan.plan_cases).selectinload(PlanCase.test_case),
                selectinload(TestPlan.environment).selectinload(Environment.variables),
            )
        )
        if plan is None:
            raise TestPlanNotFoundError(f"Test plan not found: {plan_id}")
        return plan

    def _load_test_case(self, case_id: uuid.UUID) -> TestCase:
        test_case = self.db.get(TestCase, case_id)
        if test_case is None:
            raise TestCaseNotFoundError(f"Test case not found: {case_id}")
        return test_case

    def _load_environment(self, env_id: uuid.UUID) -> Environment:
        environment = self.db.scalar(
            select(Environment)
            .where(Environment.id == env_id)
            .options(selectinload(Environment.variables))
        )
        if environment is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")
        return environment

    @staticmethod
    def _build_variable_map(variables: list[EnvironmentVariable]) -> dict[str, str]:
        return build_variable_map({item.key: item.value for item in variables})

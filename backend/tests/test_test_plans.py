import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Plan Project", "description": "For test plans"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_environment(client: TestClient, auth_headers: dict[str, str]) -> str:
    name = f"env_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": name, "is_default": False},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_case(
    client: TestClient,
    auth_headers: dict[str, str],
    project_id: str,
    name: str,
    status: str = "active",
) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
        json={"name": name, "status": status},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_test_plan_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    base_url = f"/api/v1/projects/{project_id}/plans"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={
            "name": "Smoke Plan",
            "environment_id": environment_id,
            "cron_expression": "0 2 * * *",
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    plan_id = created["id"]
    assert created["name"] == "Smoke Plan"
    assert created["environment_id"] == environment_id
    assert created["cron_expression"] == "0 2 * * *"
    assert created["is_enabled"] is True
    assert created["project_id"] == project_id
    assert created["case_count"] == 0
    assert created["environment_name"]

    list_response = client.get(base_url, headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["case_count"] == 0

    get_response = client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert get_response.status_code == 200
    detail = get_response.json()
    assert detail["name"] == "Smoke Plan"
    assert detail["cases"] == []

    update_response = client.put(
        f"{base_url}/{plan_id}",
        headers=auth_headers,
        json={"name": "Nightly Plan", "is_enabled": False},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Nightly Plan"
    assert updated["is_enabled"] is False

    delete_response = client.delete(f"{base_url}/{plan_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    missing_response = client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert missing_response.status_code == 404


def test_test_plan_bind_and_unbind_cases(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_a = _create_case(client, auth_headers, project_id, "Case A")
    case_b = _create_case(client, auth_headers, project_id, "Case B")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Regression", "environment_id": environment_id},
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    bind_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [case_a, case_b]},
    )
    assert bind_response.status_code == 200
    bound = bind_response.json()
    assert bound["case_count"] == 2
    assert len(bound["cases"]) == 2
    assert bound["cases"][0]["case_id"] == case_a
    assert bound["cases"][0]["case_name"] == "Case A"
    assert bound["cases"][0]["sort_order"] == 0
    assert bound["cases"][0]["status"] == "active"
    assert bound["cases"][1]["case_id"] == case_b
    assert bound["cases"][1]["sort_order"] == 1
    assert bound["cases"][1]["status"] == "active"

    duplicate_bind_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [case_a]},
    )
    assert duplicate_bind_response.status_code == 200
    assert duplicate_bind_response.json()["case_count"] == 2

    unbind_response = client.delete(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases/{case_a}",
        headers=auth_headers,
    )
    assert unbind_response.status_code == 200
    remaining = unbind_response.json()
    assert remaining["case_count"] == 1
    assert remaining["cases"][0]["case_id"] == case_b


def test_test_plan_bind_rejects_draft_case(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    active_case = _create_case(client, auth_headers, project_id, "Active Case")
    draft_case = _create_case(client, auth_headers, project_id, "Draft Case", status="draft")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]

    bind_draft_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [draft_case]},
    )
    assert bind_draft_response.status_code == 400
    assert "Only active test cases can be bound" in bind_draft_response.json()["detail"]
    assert "Draft Case" in bind_draft_response.json()["detail"]

    bind_mixed_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [active_case, draft_case]},
    )
    assert bind_mixed_response.status_code == 400

    detail_response = client.get(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["case_count"] == 0


def test_test_plan_bind_rejects_exceeding_case_limit(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.test_plan_service.PLAN_CASE_MAX_COUNT", 2)

    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_a = _create_case(client, auth_headers, project_id, "Case A")
    case_b = _create_case(client, auth_headers, project_id, "Case B")
    case_c = _create_case(client, auth_headers, project_id, "Case C")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Limited Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]
    bind_url = f"/api/v1/projects/{project_id}/plans/{plan_id}/cases"

    first_bind = client.post(
        bind_url,
        headers=auth_headers,
        json={"case_ids": [case_a, case_b]},
    )
    assert first_bind.status_code == 200
    assert first_bind.json()["case_count"] == 2

    overflow_bind = client.post(
        bind_url,
        headers=auth_headers,
        json={"case_ids": [case_c]},
    )
    assert overflow_bind.status_code == 400
    assert "at most 2 cases" in overflow_bind.json()["detail"]

    detail_response = client.get(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["case_count"] == 2


def test_test_plan_create_rejects_missing_environment(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Bad Plan", "environment_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_test_plan_bind_rejects_foreign_case(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    other_project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    foreign_case_id = _create_case(client, auth_headers, other_project_id, "Foreign")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]

    bind_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [foreign_case_id]},
    )
    assert bind_response.status_code == 404


def test_test_plan_unbind_not_bound_case(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_id = _create_case(client, auth_headers, project_id, "Loose Case")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]

    response = client.delete(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases/{case_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Case is not bound to this plan"


def test_test_plan_endpoints_require_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    base_url = f"/api/v1/projects/{project_id}/plans"

    assert client.get(base_url).status_code == 403
    assert client.post(
        base_url,
        json={"name": "Unauthorized", "environment_id": str(uuid.uuid4())},
    ).status_code == 403


def test_test_plan_missing_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_test_plan_create_rejects_invalid_cron(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={
            "name": "Bad Cron Plan",
            "environment_id": environment_id,
            "cron_expression": "invalid cron",
        },
    )
    assert response.status_code == 422


def test_test_plan_create_rejects_enabled_without_cron(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={
            "name": "Enabled No Cron",
            "environment_id": environment_id,
            "is_enabled": True,
        },
    )
    assert response.status_code == 422


def test_test_plan_create_accepts_valid_cron(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={
            "name": "Morning Plan",
            "environment_id": environment_id,
            "cron_expression": "0 9 * * *",
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["cron_expression"] == "0 9 * * *"
    assert response.json()["is_enabled"] is True


def test_test_plan_update_rejects_enable_without_cron(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    create_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Plan", "environment_id": environment_id},
    )
    plan_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
        json={"is_enabled": True},
    )
    assert update_response.status_code == 400
    assert "required" in update_response.json()["detail"].lower()


def test_test_plan_includes_environment_name(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    create_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Env Plan", "environment_id": environment_id},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["environment_id"] == environment_id
    assert created["environment_name"]

    list_response = client.get(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["environment_name"] == created["environment_name"]


def test_test_plan_update_environment(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_a = _create_environment(client, auth_headers)
    environment_b = _create_environment(client, auth_headers)

    create_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Switch Env", "environment_id": environment_a},
    )
    plan_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
        json={"environment_id": environment_b},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["environment_id"] == environment_b
    assert updated["environment_name"]
    assert updated["environment_name"] != create_response.json()["environment_name"]


def test_test_plan_notify_on_complete(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    create_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={
            "name": "Notify Plan",
            "environment_id": environment_id,
            "notify_on_complete": False,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["notify_on_complete"] is False

    plan_id = created["id"]
    update_response = client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
        json={"notify_on_complete": True},
    )
    assert update_response.status_code == 200
    assert update_response.json()["notify_on_complete"] is True

    detail_response = client.get(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["notify_on_complete"] is True


@patch("app.api.test_plans.execute_test_plan")
def test_run_test_plan_api(
    mock_execute: MagicMock,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    from datetime import datetime, timezone

    from app.models.test_plan import PlanRun

    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_id = _create_case(client, auth_headers, project_id, "Run Case")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Run Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]
    client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [case_id]},
    )

    plan_run = PlanRun(
        id=uuid.uuid4(),
        plan_id=uuid.UUID(plan_id),
        status="completed",
        total_count=1,
        pass_count=1,
        fail_count=0,
        allure_report_url="http://localhost:8000/reports/demo/index.html",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    mock_execute.return_value = (plan_run, MagicMock())

    response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/run",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["pass_count"] == 1
    assert body["allure_report_url"] is not None


@patch("app.services.plan_execution_service.notify_plan_run_completed")
@patch("app.services.plan_execution_service.generate_allure_report")
@patch("app.services.plan_execution_service.AllureReportWriter")
@patch("app.services.plan_execution_service.TestRunner")
def test_list_plan_runs_api(
    mock_runner_cls: MagicMock,
    mock_writer_cls: MagicMock,
    mock_generate: MagicMock,
    mock_notify: MagicMock,
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.test_runner import (
        HttpResponseSnapshot,
        PlanRunCaseResult,
        PlanRunResult,
        PreparedRequest,
        SingleRunResult,
    )

    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setenv("REPORT_BASE_URL", "http://localhost:8000/reports")
    get_settings.cache_clear()

    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_id = _create_case(client, auth_headers, project_id, "History Case")

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "History Plan", "environment_id": environment_id},
    )
    plan_id = plan_response.json()["id"]
    client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/cases",
        headers=auth_headers,
        json={"case_ids": [case_id]},
    )

    single = SingleRunResult(
        case_id=uuid.UUID(case_id),
        case_name="History Case",
        environment_id=uuid.UUID(environment_id),
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
        passed=False,
        response=HttpResponseSnapshot(status_code=500, body="err", elapsed_ms=1.0),
        assertions=None,
        error="status code mismatch",
    )
    mock_runner_cls.return_value.run_plan.return_value = PlanRunResult(
        plan_id=uuid.UUID(plan_id),
        plan_name="History Plan",
        environment_id=uuid.UUID(environment_id),
        environment_name="dev",
        trigger="manual",
        total_count=1,
        pass_count=0,
        fail_count=1,
        passed=False,
        case_results=[
            PlanRunCaseResult(
                case_id=uuid.UUID(case_id),
                case_name="History Case",
                sort_order=0,
                passed=False,
                result=single,
            )
        ],
    )
    mock_writer_cls.return_value = MagicMock()
    mock_generate.return_value = tmp_path / "reports" / "run"

    run_response = client.post(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/run",
        headers=auth_headers,
    )
    assert run_response.status_code == 200

    list_response = client.get(
        f"/api/v1/projects/{project_id}/plans/{plan_id}/runs",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    runs = list_response.json()
    assert len(runs) == 1
    assert runs[0]["fail_count"] == 1
    get_settings.cache_clear()

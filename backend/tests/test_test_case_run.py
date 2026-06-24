import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services.test_runner import HttpResponseSnapshot


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Run Project", "description": "For run API"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_environment(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": f"dev_{uuid.uuid4().hex[:6]}", "is_default": False},
    )
    assert response.status_code == 201
    environment_id = response.json()["id"]

    save_vars = client.put(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
        json={
            "variables": [
                {"key": "base_url", "value": "http://localhost:8080", "is_secret": False},
            ]
        },
    )
    assert save_vars.status_code == 200
    return environment_id


def _create_test_case(client: TestClient, auth_headers: dict[str, str], project_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
        json={
            "name": "Health check",
            "request_json": {
                "method": "GET",
                "url": "{{base_url}}/health",
                "headers": [],
                "query": [],
                "body": {"type": "none", "content": ""},
            },
            "assertions_json": {
                "status_code": 200,
                "max_response_time_ms": 3000,
                "body_rules": [{"type": "contains", "value": "ok"}],
            },
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@patch("app.services.test_runner.execute_http_request")
def test_run_test_case_returns_structured_result(
    mock_execute: MagicMock,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    mock_execute.return_value = HttpResponseSnapshot(
        status_code=200,
        body='{"status":"ok"}',
        elapsed_ms=88.6,
    )

    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_id = _create_test_case(client, auth_headers, project_id)

    response = client.post(
        f"/api/v1/projects/{project_id}/cases/{case_id}/run",
        headers=auth_headers,
        json={"environment_id": environment_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert data["case_name"] == "Health check"
    assert data["environment_id"] == environment_id
    assert data["passed"] is True
    assert data["error"] is None
    assert data["prepared_request"]["url"] == "http://localhost:8080/health"
    assert data["response"]["status_code"] == 200
    assert data["response"]["elapsed_ms"] == 88.6
    assert data["assertions"]["passed"] is True
    assert len(data["assertions"]["checks"]) == 3


@patch("app.services.test_runner.execute_http_request")
def test_run_test_case_reports_assertion_failure(
    mock_execute: MagicMock,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    mock_execute.return_value = HttpResponseSnapshot(
        status_code=500,
        body='{"error":"failed"}',
        elapsed_ms=200.0,
    )

    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)
    case_id = _create_test_case(client, auth_headers, project_id)

    response = client.post(
        f"/api/v1/projects/{project_id}/cases/{case_id}/run",
        headers=auth_headers,
        json={"environment_id": environment_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["passed"] is False
    assert data["assertions"]["passed"] is False


def test_run_test_case_requires_auth(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/projects/{uuid.uuid4()}/cases/{uuid.uuid4()}/run",
        json={"environment_id": str(uuid.uuid4())},
    )
    assert response.status_code == 403


def test_run_test_case_missing_environment(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    case_id = _create_test_case(client, auth_headers, project_id)

    response = client.post(
        f"/api/v1/projects/{project_id}/cases/{case_id}/run",
        headers=auth_headers,
        json={"environment_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


def test_run_test_case_missing_case(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    environment_id = _create_environment(client, auth_headers)

    response = client.post(
        f"/api/v1/projects/{project_id}/cases/{uuid.uuid4()}/run",
        headers=auth_headers,
        json={"environment_id": environment_id},
    )

    assert response.status_code == 404

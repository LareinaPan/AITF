import uuid

from fastapi.testclient import TestClient


def _create_pt_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={"name": "PT Scenario Test Project", "description": "For scenario CRUD"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_pt_scenario_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_pt_project(client, auth_headers)

    create_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
        json={
            "name": "Login Load Test",
            "description": "Login API stress scenario",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    scenario_id = created["id"]
    assert created["name"] == "Login Load Test"
    assert created["description"] == "Login API stress scenario"
    assert created["pt_project_id"] == project_id
    assert created["script_id"]
    assert created["parse_status"] == "pending"
    assert created["last_run_status"] is None

    list_response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Login Load Test"

    update_response = client.put(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}",
        headers=auth_headers,
        json={"name": "Updated Scenario", "description": "Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Scenario"

    stats_response = client.get(
        f"/api/v1/pt-projects/{project_id}/stats",
        headers=auth_headers,
    )
    assert stats_response.status_code == 200
    assert stats_response.json()["scenario_count"] == 1

    delete_response = client.delete(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_pt_scenario_endpoints_require_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    response = client.get(f"/api/v1/pt-projects/{project_id}/scenarios")
    assert response.status_code == 403


def test_pt_scenario_project_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        f"/api/v1/pt-projects/{uuid.uuid4()}/scenarios",
        headers=auth_headers,
        json={"name": "Missing Project Scenario"},
    )
    assert response.status_code == 404


def test_create_pt_scenario_creates_script_row(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_pt_project(client, auth_headers)
    create_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
        json={"name": "Script Placeholder Scenario"},
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["script_id"]
    assert payload["parse_status"] == "pending"

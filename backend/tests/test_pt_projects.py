import uuid

from fastapi.testclient import TestClient


def test_pt_project_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={
            "name": "Demo PT Project",
            "description": "Performance testing demo",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["name"] == "Demo PT Project"
    assert created["description"] == "Performance testing demo"
    assert created["created_by"]
    assert created["created_by_username"]

    list_response = client.get("/api/v1/pt-projects", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/pt-projects/{project_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Demo PT Project"

    update_response = client.put(
        f"/api/v1/pt-projects/{project_id}",
        headers=auth_headers,
        json={"name": "Updated PT Project", "description": "Updated description"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated PT Project"

    delete_response = client.delete(
        f"/api/v1/pt-projects/{project_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = client.get(
        f"/api/v1/pt-projects/{project_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_pt_project_endpoints_require_auth(client: TestClient) -> None:
    response = client.get("/api/v1/pt-projects")
    assert response.status_code == 403

    create_response = client.post(
        "/api/v1/pt-projects",
        json={"name": "Unauthorized"},
    )
    assert create_response.status_code == 403


def test_get_missing_pt_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(
        f"/api/v1/pt-projects/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_pt_project_stats(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={"name": "Stats PT Project", "description": "For stats API"},
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    stats_response = client.get(
        f"/api/v1/pt-projects/{project_id}/stats",
        headers=auth_headers,
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["scenario_count"] == 0
    assert stats["run_count"] == 0
    assert stats["last_run_at"] is None
    assert stats["last_run_status"] is None

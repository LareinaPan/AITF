import uuid

from fastapi.testclient import TestClient


def test_project_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={
            "name": "Demo Project",
            "description": "First project",
            "feishu_webhook_url": "https://example.com/hook",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["name"] == "Demo Project"
    assert created["description"] == "First project"
    assert created["created_by"]
    assert created["created_by_username"]

    list_response = client.get("/api/v1/projects", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Demo Project"

    update_response = client.put(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "Updated Project", "description": "Updated description"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Project"

    delete_response = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_project_endpoints_require_auth(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 403

    create_response = client.post(
        "/api/v1/projects",
        json={"name": "Unauthorized"},
    )
    assert create_response.status_code == 403


def test_get_missing_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(
        f"/api/v1/projects/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404

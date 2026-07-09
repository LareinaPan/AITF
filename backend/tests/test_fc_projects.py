import uuid

from fastapi.testclient import TestClient


def test_fc_project_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={
            "name": "Demo FC Project",
            "description": "Functional case generation demo",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["name"] == "Demo FC Project"
    assert created["description"] == "Functional case generation demo"
    assert created["created_by"]
    assert created["created_by_username"]

    list_response = client.get("/api/v1/fc-projects", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/fc-projects/{project_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Demo FC Project"

    update_response = client.put(
        f"/api/v1/fc-projects/{project_id}",
        headers=auth_headers,
        json={"name": "Updated FC Project", "description": "Updated description"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated FC Project"

    delete_response = client.delete(
        f"/api/v1/fc-projects/{project_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = client.get(
        f"/api/v1/fc-projects/{project_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_fc_project_endpoints_require_auth(client: TestClient) -> None:
    response = client.get("/api/v1/fc-projects")
    assert response.status_code == 403

    create_response = client.post(
        "/api/v1/fc-projects",
        json={"name": "Unauthorized"},
    )
    assert create_response.status_code == 403


def test_get_missing_fc_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(
        f"/api/v1/fc-projects/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_fc_project_stats(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Stats Project", "description": "For stats API"},
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    stats_response = client.get(
        f"/api/v1/fc-projects/{project_id}/stats",
        headers=auth_headers,
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["doc_count"] == 0
    assert stats["experience_case_count"] == 0
    assert stats["active_case_count"] == 0
    assert stats["draft_case_count"] == 0
    assert stats["batch_count"] == 0
    assert stats["last_batch_at"] is None

    client.post(
        f"/api/v1/fc-projects/{project_id}/docs/upload",
        headers=auth_headers,
        files={"file": ("req.txt", b"requirement text", "text/plain")},
    )
    client.post(
        f"/api/v1/fc-projects/{project_id}/cases",
        headers=auth_headers,
        json={
            "module": "登录",
            "title": "active case",
            "steps": "1. step",
            "expected_result": "ok",
            "status": "active",
        },
    )

    stats_response = client.get(
        f"/api/v1/fc-projects/{project_id}/stats",
        headers=auth_headers,
    )
    stats = stats_response.json()
    assert stats["doc_count"] == 1
    assert stats["active_case_count"] == 1


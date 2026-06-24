import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import ApiEndpoint


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Case Project", "description": "For test cases"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_test_case_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers)
    base_url = f"/api/v1/projects/{project_id}/cases"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={
            "name": "Login API",
            "description": "Verify login",
            "priority": "P0",
            "request_json": {
                "method": "POST",
                "url": "{{base_url}}/api/login",
                "headers": [{"key": "Content-Type", "value": "application/json"}],
                "query": [],
                "body": {"type": "json", "content": '{"username":"test"}'},
            },
            "assertions_json": {
                "status_code": 200,
                "max_response_time_ms": 3000,
                "body_rules": [{"type": "contains", "value": "success"}],
            },
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    case_id = created["id"]
    assert created["name"] == "Login API"
    assert created["status"] == "active"
    assert created["priority"] == "P0"
    assert created["project_id"] == project_id
    assert created["request_json"]["method"] == "POST"

    list_response = client.get(base_url, headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"{base_url}/{case_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Login API"

    update_response = client.put(
        f"{base_url}/{case_id}",
        headers=auth_headers,
        json={"name": "Login API Updated", "priority": "P1", "status": "draft"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Login API Updated"
    assert updated["priority"] == "P1"
    assert updated["status"] == "draft"

    delete_response = client.delete(f"{base_url}/{case_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    missing_response = client.get(f"{base_url}/{case_id}", headers=auth_headers)
    assert missing_response.status_code == 404


def test_test_case_create_defaults_status_active(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
        json={"name": "Minimal case"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "active"
    assert data["priority"] == "P2"
    assert data["request_json"]["method"] == "GET"
    assert data["assertions_json"]["status_code"] == 200


def test_test_case_endpoints_require_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    base_url = f"/api/v1/projects/{project_id}/cases"

    assert client.get(base_url).status_code == 403
    assert client.post(base_url, json={"name": "Unauthorized"}).status_code == 403


def test_test_case_missing_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_test_case_not_found_in_project(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.get(
        f"/api/v1/projects/{project_id}/cases/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_test_case_invalid_priority(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
        json={"name": "Bad priority", "priority": "P9"},
    )
    assert response.status_code == 422


def test_confirm_draft_test_case(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers)
    base_url = f"/api/v1/projects/{project_id}/cases"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={"name": "AI draft case", "status": "draft"},
    )
    assert create_response.status_code == 201
    case_id = create_response.json()["id"]
    assert create_response.json()["status"] == "draft"

    confirm_response = client.post(
        f"{base_url}/{case_id}/confirm",
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["id"] == case_id
    assert confirmed["status"] == "active"
    assert confirmed["name"] == "AI draft case"

    get_response = client.get(f"{base_url}/{case_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "active"


def test_confirm_test_case_rejects_non_draft(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    base_url = f"/api/v1/projects/{project_id}/cases"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={"name": "Active case"},
    )
    assert create_response.status_code == 201
    case_id = create_response.json()["id"]

    confirm_response = client.post(
        f"{base_url}/{case_id}/confirm",
        headers=auth_headers,
    )
    assert confirm_response.status_code == 400
    assert confirm_response.json()["detail"] == "Only draft test cases can be confirmed"


def test_confirm_test_case_requires_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    case_id = uuid.uuid4()
    response = client.post(f"/api/v1/projects/{project_id}/cases/{case_id}/confirm")
    assert response.status_code == 403


def _seed_endpoint(migrated_db: str, project_id: uuid.UUID) -> ApiEndpoint:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        endpoint = ApiEndpoint(
            project_id=project_id,
            method="GET",
            path="/api/users",
            summary="List users",
        )
        session.add(endpoint)
        session.commit()
        session.refresh(endpoint)
        result = endpoint

    engine.dispose()
    return result


def test_test_case_list_filter_by_api_endpoint(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    endpoint = _seed_endpoint(migrated_db, project_id)
    cases_url = f"/api/v1/projects/{project_id}/cases"

    linked_response = client.post(
        cases_url,
        headers=auth_headers,
        json={"name": "Linked case", "api_endpoint_id": str(endpoint.id)},
    )
    assert linked_response.status_code == 201

    unlinked_response = client.post(
        cases_url,
        headers=auth_headers,
        json={"name": "Unlinked case"},
    )
    assert unlinked_response.status_code == 201

    filtered_response = client.get(
        cases_url,
        headers=auth_headers,
        params={"api_endpoint_id": str(endpoint.id)},
    )
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert len(filtered) == 1
    assert filtered[0]["name"] == "Linked case"
    assert filtered[0]["api_endpoint_id"] == str(endpoint.id)


def test_test_case_create_rejects_foreign_api_endpoint(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    other_project_id = uuid.UUID(_create_project(client, auth_headers))
    foreign_endpoint = _seed_endpoint(migrated_db, other_project_id)

    response = client.post(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
        json={"name": "Bad link", "api_endpoint_id": str(foreign_endpoint.id)},
    )
    assert response.status_code == 404


def test_confirm_test_case_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/cases/{uuid.uuid4()}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 404

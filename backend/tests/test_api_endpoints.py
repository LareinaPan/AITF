import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import ApiEndpoint


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "API Project", "description": "For API endpoints"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_endpoints(migrated_db: str, project_id: uuid.UUID, count: int) -> list[ApiEndpoint]:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        endpoints = [
            ApiEndpoint(
                project_id=project_id,
                method="GET",
                path=f"/api/resource-{index}",
                summary=f"Resource {index}",
            )
            for index in range(count)
        ]
        session.add_all(endpoints)
        session.commit()
        for endpoint in endpoints:
            session.refresh(endpoint)
        result = list(endpoints)

    engine.dispose()
    return result


def test_list_and_get_api_endpoints(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    seeded = _seed_endpoints(migrated_db, project_id, 3)
    base_url = f"/api/v1/projects/{project_id}/apis"

    list_response = client.get(base_url, headers=auth_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert len(payload["items"]) == 3
    assert payload["items"][0]["method"] == "GET"
    assert payload["items"][0]["path"].startswith("/api/resource-")
    assert payload["items"][0]["test_case_count"] == 0

    detail_response = client.get(f"{base_url}/{seeded[0].id}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == str(seeded[0].id)
    assert detail["project_id"] == str(project_id)
    assert detail["summary"] == "Resource 0"
    assert detail["parameters_json"] == []
    assert detail["responses_json"] == {}


def test_list_api_endpoints_pagination(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    _seed_endpoints(migrated_db, project_id, 5)
    base_url = f"/api/v1/projects/{project_id}/apis"

    page_one = client.get(f"{base_url}?page=1&page_size=2", headers=auth_headers)
    assert page_one.status_code == 200
    data = page_one.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2

    page_three = client.get(f"{base_url}?page=3&page_size=2", headers=auth_headers)
    assert page_three.status_code == 200
    assert len(page_three.json()["items"]) == 1


def test_api_endpoints_require_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    base_url = f"/api/v1/projects/{project_id}/apis"

    assert client.get(base_url).status_code == 403
    assert client.get(f"{base_url}/{uuid.uuid4()}").status_code == 403


def test_api_endpoints_missing_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_api_endpoint_not_found_in_project(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.get(
        f"/api/v1/projects/{project_id}/apis/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_api_endpoint_wrong_project(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_a = uuid.UUID(_create_project(client, auth_headers))
    project_b = uuid.UUID(_create_project(client, auth_headers))
    seeded = _seed_endpoints(migrated_db, project_a, 1)

    response = client.get(
        f"/api/v1/projects/{project_b}/apis/{seeded[0].id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_list_api_endpoints_empty(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_delete_api_endpoint(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    seeded = _seed_endpoints(migrated_db, project_id, 2)
    base_url = f"/api/v1/projects/{project_id}/apis"

    delete_response = client.delete(f"{base_url}/{seeded[0].id}", headers=auth_headers)
    assert delete_response.status_code == 204

    list_response = client.get(base_url, headers=auth_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(seeded[1].id)

    missing_response = client.get(f"{base_url}/{seeded[0].id}", headers=auth_headers)
    assert missing_response.status_code == 404


def test_list_api_endpoints_includes_test_case_count(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    seeded = _seed_endpoints(migrated_db, project_id, 2)
    base_url = f"/api/v1/projects/{project_id}/cases"

    create_one = client.post(
        base_url,
        headers=auth_headers,
        json={"name": "Case 1", "api_endpoint_id": str(seeded[0].id)},
    )
    assert create_one.status_code == 201

    create_two = client.post(
        base_url,
        headers=auth_headers,
        json={"name": "Case 2", "api_endpoint_id": str(seeded[0].id)},
    )
    assert create_two.status_code == 201

    create_three = client.post(
        base_url,
        headers=auth_headers,
        json={"name": "Case 3", "api_endpoint_id": str(seeded[1].id)},
    )
    assert create_three.status_code == 201

    list_response = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    items = {item["id"]: item["test_case_count"] for item in list_response.json()["items"]}
    assert items[str(seeded[0].id)] == 2
    assert items[str(seeded[1].id)] == 1


def test_delete_api_endpoint_requires_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    api_id = uuid.uuid4()
    response = client.delete(f"/api/v1/projects/{project_id}/apis/{api_id}")
    assert response.status_code == 403


def test_delete_api_endpoint_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.delete(
        f"/api/v1/projects/{project_id}/apis/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404

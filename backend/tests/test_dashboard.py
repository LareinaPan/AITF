import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import ApiEndpoint
from app.models.test_case import TestCase


def _create_project(client: TestClient, auth_headers: dict[str, str], name: str) -> uuid.UUID:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": name, "description": "Dashboard test"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _seed_project_data(
    migrated_db: str,
    project_id: uuid.UUID,
    *,
    api_count: int,
    active_cases: int,
    draft_cases: int,
) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        session.add_all(
            [
                ApiEndpoint(
                    project_id=project_id,
                    method="GET",
                    path=f"/api/item-{index}",
                    summary=f"Item {index}",
                )
                for index in range(api_count)
            ],
        )
        session.add_all(
            [
                TestCase(
                    project_id=project_id,
                    name=f"Active case {index}",
                    status="active",
                )
                for index in range(active_cases)
            ],
        )
        session.add_all(
            [
                TestCase(
                    project_id=project_id,
                    name=f"Draft case {index}",
                    status="draft",
                )
                for index in range(draft_cases)
            ],
        )
        session.commit()

    engine.dispose()


def test_dashboard_stats_aggregates_across_projects(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_a = _create_project(client, auth_headers, "Alpha")
    project_b = _create_project(client, auth_headers, "Beta")
    _seed_project_data(migrated_db, project_a, api_count=3, active_cases=2, draft_cases=1)
    _seed_project_data(migrated_db, project_b, api_count=1, active_cases=4, draft_cases=2)

    response = client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_apis"] == 4
    assert payload["total_cases"] == 6

    by_project = {item["name"]: item for item in payload["by_project"]}
    assert len(by_project) == 2
    assert by_project["Alpha"]["apis"] == 3
    assert by_project["Alpha"]["cases"] == 2
    assert by_project["Beta"]["apis"] == 1
    assert by_project["Beta"]["cases"] == 4


def test_dashboard_stats_empty_projects(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    _create_project(client, auth_headers, "Empty")

    response = client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_apis"] == 0
    assert payload["total_cases"] == 0
    assert len(payload["by_project"]) == 1
    assert payload["by_project"][0]["name"] == "Empty"
    assert payload["by_project"][0]["apis"] == 0
    assert payload["by_project"][0]["cases"] == 0


def test_dashboard_stats_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code == 403

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import ApiEndpoint
from app.services.ai_generator import GeneratedTestCases

SAMPLE_GENERATED_CASE = {
    "name": "Create user success",
    "description": "Valid payload",
    "priority": "P1",
    "request_json": {
        "method": "POST",
        "url": "{{base_url}}/api/users",
        "headers": [{"key": "Content-Type", "value": "application/json"}],
        "query": [],
        "body": {"type": "json", "content": '{"name":"demo"}'},
    },
    "assertions_json": {
        "status_code": 201,
        "max_response_time_ms": 3000,
        "body_rules": [{"type": "contains", "value": "id"}],
    },
}


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "AI Project", "description": "For AI generate"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_endpoint(migrated_db: str, project_id: uuid.UUID) -> ApiEndpoint:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        endpoint = ApiEndpoint(
            project_id=project_id,
            method="POST",
            path="/api/users",
            summary="Create user",
        )
        session.add(endpoint)
        session.commit()
        session.refresh(endpoint)
        result = endpoint

    engine.dispose()
    return result


@patch("app.api.api_endpoints.generate_test_case_candidates")
def test_ai_generate_creates_draft_cases(
    mock_generate,
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    endpoint = _seed_endpoint(migrated_db, project_id)
    mock_generate.return_value = GeneratedTestCases(
        cases=[SAMPLE_GENERATED_CASE],
        rejected_count=1,
        requested_count=3,
        raw_count=2,
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/apis/{endpoint.id}/ai-generate",
        headers=auth_headers,
        json={
            "positive_count": 2,
            "boundary_count": 0,
            "exception_count": 1,
            "auth_count": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rejected_count"] == 1
    assert payload["requested_count"] == 3
    assert payload["raw_count"] == 2
    assert len(payload["cases"]) == 1
    created = payload["cases"][0]
    assert created["status"] == "draft"
    assert created["name"] == "Create user success"
    assert created["api_endpoint_id"] == str(endpoint.id)
    assert created["project_id"] == str(project_id)

    list_response = client.get(
        f"/api/v1/projects/{project_id}/cases",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["status"] == "draft"


@patch("app.api.api_endpoints.generate_test_case_candidates")
def test_ai_generate_missing_endpoint(
    mock_generate,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/apis/{uuid.uuid4()}/ai-generate",
        headers=auth_headers,
        json={"positive_count": 1},
    )
    assert response.status_code == 404
    mock_generate.assert_not_called()


def test_ai_generate_requires_auth(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/projects/{uuid.uuid4()}/apis/{uuid.uuid4()}/ai-generate",
        json={"positive_count": 1},
    )
    assert response.status_code == 403


def test_ai_generate_rejects_zero_count(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    project_id = uuid.UUID(_create_project(client, auth_headers))
    endpoint = _seed_endpoint(migrated_db, project_id)

    response = client.post(
        f"/api/v1/projects/{project_id}/apis/{endpoint.id}/ai-generate",
        headers=auth_headers,
        json={
            "positive_count": 0,
            "boundary_count": 0,
            "exception_count": 0,
            "auth_count": 0,
        },
    )
    assert response.status_code == 422


@patch("app.api.api_endpoints.generate_test_case_candidates")
def test_ai_generate_maps_llm_configuration_error(
    mock_generate,
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_db: str,
) -> None:
    from app.services.ai_generator import LLMConfigurationError

    project_id = uuid.UUID(_create_project(client, auth_headers))
    endpoint = _seed_endpoint(migrated_db, project_id)
    mock_generate.side_effect = LLMConfigurationError("OPENAI_API_KEY is not configured")

    response = client.post(
        f"/api/v1/projects/{project_id}/apis/{endpoint.id}/ai-generate",
        headers=auth_headers,
        json={"positive_count": 1},
    )
    assert response.status_code == 503

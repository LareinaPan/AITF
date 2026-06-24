import io
import json
import uuid

from fastapi.testclient import TestClient

from tests.test_openapi_parser import SAMPLE_OPENAPI


def _create_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "OpenAPI Project", "description": "For upload"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_openapi_creates_endpoints(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    content = json.dumps(SAMPLE_OPENAPI).encode("utf-8")

    response = client.post(
        f"/api/v1/projects/{project_id}/openapi/upload",
        headers=auth_headers,
        files={"file": ("demo.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "demo.json"
    assert payload["created"] == 3
    assert payload["updated"] == 0
    assert payload["total"] == 3

    list_response = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 3


def test_upload_openapi_updates_existing_endpoints(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    content = json.dumps(SAMPLE_OPENAPI).encode("utf-8")
    upload_url = f"/api/v1/projects/{project_id}/openapi/upload"
    files = {"file": ("demo.json", io.BytesIO(content), "application/json")}

    first = client.post(upload_url, headers=auth_headers, files=files)
    assert first.status_code == 200
    assert first.json()["created"] == 3

    second = client.post(upload_url, headers=auth_headers, files=files)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["created"] == 0
    assert second_payload["updated"] == 3
    assert second_payload["total"] == 3


def test_upload_openapi_rejects_invalid_file(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/openapi/upload",
        headers=auth_headers,
        files={"file": ("demo.json", io.BytesIO(b"{invalid"), "application/json")},
    )
    assert response.status_code == 400


def test_upload_openapi_requires_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/projects/{project_id}/openapi/upload",
        files={"file": ("demo.json", io.BytesIO(b"{}"), "application/json")},
    )
    assert response.status_code == 403


def test_upload_openapi_missing_project(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/projects/{project_id}/openapi/upload",
        headers=auth_headers,
        files={"file": ("demo.json", io.BytesIO(b"{}"), "application/json")},
    )
    assert response.status_code == 404

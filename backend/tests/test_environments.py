import uuid

from fastapi.testclient import TestClient


def test_environment_crud_and_variables(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": "dev", "is_default": True},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    environment_id = created["id"]
    assert created["name"] == "dev"
    assert created["is_default"] is True

    list_response = client.get("/api/v1/environments", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    save_vars_response = client.put(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
        json={
            "variables": [
                {
                    "key": "base_url",
                    "value": "http://localhost:8080",
                    "is_secret": False,
                },
                {"key": "token", "value": "secret-token", "is_secret": True},
            ]
        },
    )
    assert save_vars_response.status_code == 200
    variables = save_vars_response.json()
    assert len(variables) == 2
    assert variables[0]["key"] == "base_url"

    get_vars_response = client.get(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
    )
    assert get_vars_response.status_code == 200
    assert len(get_vars_response.json()) == 2

    update_response = client.put(
        f"/api/v1/environments/{environment_id}",
        headers=auth_headers,
        json={"name": "development"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "development"

    delete_response = client.delete(
        f"/api/v1/environments/{environment_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = client.get(
        f"/api/v1/environments/{environment_id}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_environment_default_flag_is_unique(client: TestClient, auth_headers: dict[str, str]) -> None:
    dev_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": "dev", "is_default": True},
    )
    test_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": "test", "is_default": True},
    )
    assert dev_response.status_code == 201
    assert test_response.status_code == 201

    environments = client.get("/api/v1/environments", headers=auth_headers).json()
    default_count = sum(1 for env in environments if env["is_default"])
    assert default_count == 1
    assert next(env for env in environments if env["name"] == "test")["is_default"] is True


def test_environment_duplicate_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {"name": "staging", "is_default": False}
    assert client.post("/api/v1/environments", headers=auth_headers, json=payload).status_code == 201
    duplicate = client.post("/api/v1/environments", headers=auth_headers, json=payload)
    assert duplicate.status_code == 409


def test_save_variables_rejects_duplicate_keys(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": "qa", "is_default": False},
    )
    environment_id = create_response.json()["id"]

    invalid = client.put(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
        json={
            "variables": [
                {"key": "base_url", "value": "http://a", "is_secret": False},
                {"key": "base_url", "value": "http://b", "is_secret": False},
            ]
        },
    )
    assert invalid.status_code == 422


def test_environment_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/environments").status_code == 403


def test_save_variables_replaces_existing(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": "prod", "is_default": False},
    )
    environment_id = create_response.json()["id"]

    client.put(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
        json={
            "variables": [
                {"key": "base_url", "value": "http://old", "is_secret": False},
                {"key": "token", "value": "old-token", "is_secret": True},
            ]
        },
    )

    replace_response = client.put(
        f"/api/v1/environments/{environment_id}/variables",
        headers=auth_headers,
        json={
            "variables": [
                {"key": "base_url", "value": "http://new", "is_secret": False},
            ]
        },
    )
    assert replace_response.status_code == 200
    variables = replace_response.json()
    assert len(variables) == 1
    assert variables[0]["value"] == "http://new"


def test_delete_environment_rejects_when_used_by_test_plan(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_response = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Env Guard Project"},
    )
    project_id = project_response.json()["id"]

    env_response = client.post(
        "/api/v1/environments",
        headers=auth_headers,
        json={"name": f"plan_env_{uuid.uuid4().hex[:8]}", "is_default": False},
    )
    environment_id = env_response.json()["id"]

    plan_response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        headers=auth_headers,
        json={"name": "Bound Plan", "environment_id": environment_id},
    )
    assert plan_response.status_code == 201

    delete_response = client.delete(
        f"/api/v1/environments/{environment_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 400
    assert "test plans" in delete_response.json()["detail"].lower()

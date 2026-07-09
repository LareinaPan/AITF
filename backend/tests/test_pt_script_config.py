from pathlib import Path

from fastapi.testclient import TestClient

DEMO_JMX = Path(__file__).resolve().parents[2] / "docs" / "demo" / "demo-load-test.jmx"


def _create_scenario_with_script(
    client: TestClient,
    auth_headers: dict[str, str],
) -> tuple[str, str, list[dict]]:
    project_response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={"name": "Config Project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    scenario_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
        json={"name": "Config Scenario"},
    )
    assert scenario_response.status_code == 201
    scenario_id = scenario_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/upload",
        headers=auth_headers,
        files={"file": ("demo-load-test.jmx", DEMO_JMX.read_bytes(), "application/xml")},
    )
    assert upload_response.status_code == 201
    samplers = upload_response.json()["script"]["parsed_plan"]["samplers"]
    return project_id, scenario_id, samplers


def _config_url(project_id: str, scenario_id: str) -> str:
    return f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/config"


def test_update_pt_script_config_duration_mode(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 50,
            "ramp_up_seconds": 10,
            "stop_mode": "duration",
            "duration_seconds": 60,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["max_concurrency"] == 50
    assert payload["ramp_up_seconds"] == 10
    assert payload["stop_mode"] == "duration"
    assert payload["duration_seconds"] == 60

    get_response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script",
        headers=auth_headers,
    )
    assert get_response.json()["duration_seconds"] == 60


def test_update_pt_script_config_request_limit_mode(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, samplers = _create_scenario_with_script(client, auth_headers)
    sampler_key = samplers[0]["key"]

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 20,
            "ramp_up_seconds": 5,
            "stop_mode": "request_limit",
            "default_max_requests": 500,
            "sampler_limits": {sampler_key: 300},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_mode"] == "request_limit"
    assert payload["default_max_requests"] == 500
    assert payload["sampler_limits"] == {sampler_key: 300}
    assert payload["duration_seconds"] is None


def test_update_pt_script_config_rejects_duration_without_seconds(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 10,
            "ramp_up_seconds": 0,
            "stop_mode": "duration",
        },
    )
    assert response.status_code == 422


def test_update_pt_script_config_rejects_request_limit_without_default(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 10,
            "ramp_up_seconds": 0,
            "stop_mode": "request_limit",
        },
    )
    assert response.status_code == 422


def test_update_pt_script_config_rejects_invalid_duration_range(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 10,
            "ramp_up_seconds": 0,
            "stop_mode": "duration",
            "duration_seconds": 5,
        },
    )
    assert response.status_code == 422


def test_update_pt_script_config_rejects_excessive_concurrency(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("PT_MAX_CONCURRENCY", "100")
    get_settings.cache_clear()

    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 200,
            "ramp_up_seconds": 0,
            "stop_mode": "duration",
            "duration_seconds": 60,
        },
    )
    assert response.status_code == 422
    get_settings.cache_clear()


def test_update_pt_script_config_rejects_unknown_sampler_key(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, _ = _create_scenario_with_script(client, auth_headers)

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 10,
            "ramp_up_seconds": 0,
            "stop_mode": "request_limit",
            "default_max_requests": 1000,
            "sampler_limits": {"sampler-unknown": 100},
        },
    )
    assert response.status_code == 400
    assert "Unknown sampler keys" in response.json()["detail"]


def test_update_pt_script_config_rejects_invalid_sampler_limit_value(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id, samplers = _create_scenario_with_script(client, auth_headers)
    sampler_key = samplers[0]["key"]

    response = client.put(
        _config_url(project_id, scenario_id),
        headers=auth_headers,
        json={
            "max_concurrency": 10,
            "ramp_up_seconds": 0,
            "stop_mode": "request_limit",
            "default_max_requests": 1000,
            "sampler_limits": {sampler_key: 0},
        },
    )
    assert response.status_code == 422

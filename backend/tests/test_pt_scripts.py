import uuid
from pathlib import Path

from fastapi.testclient import TestClient

DEMO_JMX = Path(__file__).resolve().parents[2] / "docs" / "demo" / "demo-load-test.jmx"
INVALID_JMX = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Empty Plan"/>
    <hashTree/>
  </hashTree>
</jmeterTestPlan>
"""


def _create_project_and_scenario(client: TestClient, auth_headers: dict[str, str]) -> tuple[str, str]:
    project_response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={"name": "Script Upload Project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    scenario_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
        json={"name": "Demo Scenario"},
    )
    assert scenario_response.status_code == 201
    scenario_id = scenario_response.json()["id"]
    return project_id, scenario_id


def test_get_pt_script_before_upload(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["parse_status"] == "pending"
    assert payload["parsed_plan"] is None
    assert payload["sampler_count"] == 0


def test_upload_pt_script_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)
    jmx_bytes = DEMO_JMX.read_bytes()

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/upload",
        headers=auth_headers,
        files={"file": ("demo-load-test.jmx", jmx_bytes, "application/xml")},
    )
    assert response.status_code == 201
    script = response.json()["script"]
    assert script["parse_status"] == "success"
    assert script["filename"] == "demo-load-test.jmx"
    assert script["sampler_count"] == 3
    assert script["thread_group_count"] == 1
    assert script["parsed_plan"]["samplers"][0]["method"] == "GET"

    scenario_response = client.get(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}",
        headers=auth_headers,
    )
    assert scenario_response.json()["parse_status"] == "success"


def test_upload_pt_script_parse_failure(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/upload",
        headers=auth_headers,
        files={"file": ("empty-plan.jmx", INVALID_JMX, "application/xml")},
    )
    assert response.status_code == 201
    script = response.json()["script"]
    assert script["parse_status"] == "failed"
    assert script["parse_error"]
    assert script["parsed_plan"] is None


def test_upload_pt_script_rejects_non_jmx(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/upload",
        headers=auth_headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_pt_script_requires_auth(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/pt-projects/{uuid.uuid4()}/scenarios/{uuid.uuid4()}/script/upload",
        files={"file": ("demo.jmx", b"<xml/>", "application/xml")},
    )
    assert response.status_code == 403

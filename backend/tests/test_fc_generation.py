from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.fc_ai_generator import GeneratedFcTestCases
from app.services.fc_ai_reviewer import compute_coverage_score, validate_fc_review_report

SAMPLE_CASES = [
    {
        "case_no": "FC-001",
        "module": "用户登录",
        "title": "正确密码登录",
        "preconditions": "用户已注册",
        "steps": "1. 打开登录页\n2. 输入账号密码",
        "expected_result": "登录成功",
        "priority": "P0",
        "case_type": "positive",
    }
]

PASSING_DIMENSION_SCORES = {
    "positive": 90.0,
    "negative": 85.0,
    "boundary": 80.0,
    "permission": 88.0,
    "security": 82.0,
    "compatibility": 78.0,
}


def _passing_review_report() -> dict[str, object]:
    coverage_score = compute_coverage_score(PASSING_DIMENSION_SCORES)
    return validate_fc_review_report(
        {
            "coverage_score": coverage_score,
            "dimension_scores": PASSING_DIMENSION_SCORES,
            "feature_checklist": [{"feature": "用户登录", "covered": True, "case_count": 1}],
            "gaps": [],
            "suggestions": [],
            "passed": True,
        }
    ).to_storage_dict()


def _create_fc_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Generate Project", "description": "For generation API"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _upload_requirement_doc(client: TestClient, auth_headers: dict[str, str], project_id: str) -> str:
    response = client.post(
        f"/api/v1/fc-projects/{project_id}/docs/upload",
        headers=auth_headers,
        files={"file": ("requirements.txt", b"Login module requirement details", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["doc"]["id"]


def test_start_fc_generation_runs_pipeline_to_awaiting_review(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    doc_id = _upload_requirement_doc(client, auth_headers, project_id)

    with (
        patch(
            "app.services.fc_ai_pipeline.generate_functional_test_cases",
            return_value=GeneratedFcTestCases(cases=SAMPLE_CASES, rejected_count=0, raw_count=1),
        ),
        patch(
            "app.services.fc_ai_pipeline.review_functional_test_cases",
            return_value=_passing_review_report(),
        ),
    ):
        response = client.post(
            f"/api/v1/fc-projects/{project_id}/generate",
            headers=auth_headers,
            json={
                "requirement_doc_id": doc_id,
                "experience_case_ids": [],
            },
        )

    assert response.status_code == 201
    payload = response.json()
    batch_id = payload["batch_id"]

    batch_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}",
        headers=auth_headers,
    )
    assert batch_response.status_code == 200
    batch = batch_response.json()
    assert batch["status"] == "awaiting_review"
    assert batch["coverage_score"] is not None
    assert batch["coverage_score"] >= 80.0
    assert batch["case_count"] == 1
    assert batch["review_report_json"] is not None

    cases_response = client.get(
        f"/api/v1/fc-projects/{project_id}/cases",
        headers=auth_headers,
    )
    assert cases_response.status_code == 200
    cases = cases_response.json()
    assert cases["total"] == 1
    assert len(cases["items"]) == 1
    assert cases["items"][0]["status"] == "draft"
    assert cases["items"][0]["generation_batch_id"] == batch_id


def test_start_fc_generation_rejects_unparsed_doc(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)

    response = client.post(
        f"/api/v1/fc-projects/{project_id}/generate",
        headers=auth_headers,
        json={
            "requirement_doc_id": "00000000-0000-0000-0000-000000000001",
            "experience_case_ids": [],
        },
    )
    assert response.status_code == 400

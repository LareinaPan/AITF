from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.fc_ai_generator import GeneratedFcTestCases

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
    },
    {
        "case_no": "FC-002",
        "module": "用户登录",
        "title": "错误密码登录",
        "preconditions": "用户已注册",
        "steps": "1. 输入错误密码",
        "expected_result": "提示密码错误",
        "priority": "P1",
        "case_type": "negative",
    },
]


def _create_fc_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Review Project", "description": "For review flow"},
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


def _passing_review_report() -> dict[str, object]:
    return {
        "coverage_score": 85.0,
        "dimension_scores": {
            "positive": 90.0,
            "negative": 85.0,
            "boundary": 80.0,
            "permission": 88.0,
            "security": 82.0,
            "compatibility": 78.0,
        },
        "feature_checklist": [{"feature": "用户登录", "covered": True, "case_count": 2}],
        "gaps": [],
        "suggestions": [],
        "passed": True,
    }


def _start_review_batch(client: TestClient, auth_headers: dict[str, str], project_id: str) -> str:
    doc_id = _upload_requirement_doc(client, auth_headers, project_id)
    with (
        patch(
            "app.services.fc_ai_pipeline.generate_functional_test_cases",
            return_value=GeneratedFcTestCases(cases=SAMPLE_CASES, rejected_count=0, raw_count=2),
        ),
        patch(
            "app.services.fc_ai_pipeline.review_functional_test_cases",
            return_value=_passing_review_report(),
        ),
    ):
        response = client.post(
            f"/api/v1/fc-projects/{project_id}/generate",
            headers=auth_headers,
            json={"requirement_doc_id": doc_id, "experience_case_ids": []},
        )
    assert response.status_code == 201
    return response.json()["batch_id"]


def test_list_batch_draft_cases(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    batch_id = _start_review_batch(client, auth_headers, project_id)

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/cases",
        headers=auth_headers,
    )
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 2
    assert all(case["status"] == "draft" for case in cases)


def test_confirm_partial_batch_cases(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    batch_id = _start_review_batch(client, auth_headers, project_id)

    draft_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/cases",
        headers=auth_headers,
    )
    draft_cases = draft_response.json()
    selected_id = draft_cases[0]["id"]

    confirm_response = client.post(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/confirm",
        headers=auth_headers,
        json={"case_ids": [selected_id]},
    )
    assert confirm_response.status_code == 200
    payload = confirm_response.json()
    assert payload["confirmed_count"] == 1
    assert payload["batch_status"] == "awaiting_review"

    active_response = client.get(
        f"/api/v1/fc-projects/{project_id}/cases?status=active",
        headers=auth_headers,
    )
    assert active_response.status_code == 200
    assert active_response.json()["total"] == 1

    remaining_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/cases",
        headers=auth_headers,
    )
    assert len(remaining_response.json()) == 1


def test_confirm_all_batch_cases_marks_completed(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    batch_id = _start_review_batch(client, auth_headers, project_id)

    confirm_response = client.post(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/confirm",
        headers=auth_headers,
        json={"case_ids": []},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["confirmed_count"] == 2
    assert confirm_response.json()["batch_status"] == "completed"

    batch_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}",
        headers=auth_headers,
    )
    assert batch_response.json()["status"] == "completed"


def test_reject_batch_creates_new_generation_batch(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    batch_id = _start_review_batch(client, auth_headers, project_id)

    with (
        patch(
            "app.services.fc_ai_pipeline.generate_functional_test_cases",
            return_value=GeneratedFcTestCases(cases=SAMPLE_CASES, rejected_count=0, raw_count=2),
        ),
        patch(
            "app.services.fc_ai_pipeline.review_functional_test_cases",
            return_value=_passing_review_report(),
        ),
    ):
        reject_response = client.post(
            f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/reject",
            headers=auth_headers,
            json={"feedback": "请补充忘记密码与并发登录场景"},
        )

    assert reject_response.status_code == 201
    payload = reject_response.json()
    assert payload["parent_batch_id"] == batch_id
    assert payload["status"] == "pending"
    assert payload["batch_id"] != batch_id

    batch_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{payload['batch_id']}",
        headers=auth_headers,
    )
    assert batch_response.status_code == 200


def test_update_draft_case_via_cases_api(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_fc_project(client, auth_headers)
    batch_id = _start_review_batch(client, auth_headers, project_id)

    draft_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch_id}/cases",
        headers=auth_headers,
    )
    case_id = draft_response.json()[0]["id"]

    update_response = client.put(
        f"/api/v1/fc-projects/{project_id}/cases/{case_id}",
        headers=auth_headers,
        json={"title": "编辑后的登录用例"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "编辑后的登录用例"

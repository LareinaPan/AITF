from fastapi.testclient import TestClient


def _create_fc_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Export Project", "description": "For export API"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_active_case(client: TestClient, auth_headers: dict[str, str], project_id: str) -> None:
    response = client.post(
        f"/api/v1/fc-projects/{project_id}/cases",
        headers=auth_headers,
        json={
            "case_no": "FC-001",
            "module": "用户登录",
            "title": "正确密码登录",
            "steps": "1. 登录",
            "expected_result": "成功",
            "priority": "P0",
            "case_type": "positive",
            "status": "active",
        },
    )
    assert response.status_code == 201


def test_export_fc_cases_excel(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    _create_active_case(client, auth_headers, project_id)

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/export/excel",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers.get("content-disposition", "")
    assert len(response.content) > 0


def test_export_fc_cases_xmind(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    _create_active_case(client, auth_headers, project_id)

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/export/xmind",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.xmind.workbook"
    assert len(response.content) > 0


def test_export_fc_cases_empty_returns_400(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/export/excel",
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_export_fc_cases_excel_with_chinese_project_name(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "测试项目", "description": "Chinese name export"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    _create_active_case(client, auth_headers, project_id)

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/export/excel",
        headers=auth_headers,
    )
    assert response.status_code == 200
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "filename=\"fc-export.xlsx\"" in disposition
    assert "filename*=UTF-8" in disposition

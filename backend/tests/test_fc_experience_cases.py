from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.services.fc_experience_importer import TEMPLATE_HEADERS


def _create_fc_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Experience Project", "description": "For experience cases"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _build_xlsx(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(TEMPLATE_HEADERS))
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_experience_case_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/experience-cases"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={
            "case_no": "EXP-001",
            "module": "用户登录",
            "title": "正确密码登录",
            "preconditions": "用户已注册",
            "steps": "1. 输入账号\n2. 点击登录",
            "expected_result": "登录成功",
            "priority": "P0",
            "case_type": "positive",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    case_id = created["id"]
    assert created["module"] == "用户登录"

    list_response = client.get(base_url, headers=auth_headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert len(list_payload["items"]) == 1

    update_response = client.put(
        f"{base_url}/{case_id}",
        headers=auth_headers,
        json={"title": "更新后的标题"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "更新后的标题"

    delete_response = client.delete(f"{base_url}/{case_id}", headers=auth_headers)
    assert delete_response.status_code == 204


def test_import_experience_cases(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    import_url = f"/api/v1/fc-projects/{project_id}/experience-cases/import"

    xlsx = _build_xlsx(
        [
            ("EXP-101", "订单", "创建订单", None, "1. 提交订单", "创建成功", "P1", "正向"),
            ("EXP-102", "订单", "取消订单", None, "1. 点击取消", "订单取消", "P2", "异常"),
            ("EXP-103", "支付", "支付超时", None, "1. 等待超时", "提示超时", "P1", "边界"),
            ("EXP-104", "权限", "无权限访问", None, "1. 访问页面", "403", "P0", "权限"),
            ("EXP-105", "安全", "SQL 注入", None, "1. 输入特殊字符", "被拦截", "P0", "安全"),
        ]
    )

    response = client.post(
        import_url,
        headers=auth_headers,
        files={
            "file": (
                "experience-cases.xlsx",
                xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["imported_count"] == 5
    assert payload["rejected_count"] == 0
    assert len(payload["cases"]) == 5


def test_experience_case_list_pagination(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/experience-cases"

    for index in range(3):
        response = client.post(
            base_url,
            headers=auth_headers,
            json={
                "module": "模块",
                "title": f"用例 {index}",
                "steps": "1. 步骤",
                "expected_result": "成功",
            },
        )
        assert response.status_code == 201

    page_one = client.get(f"{base_url}?page=1&page_size=2", headers=auth_headers)
    assert page_one.status_code == 200
    data = page_one.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    page_two = client.get(f"{base_url}?page=2&page_size=2", headers=auth_headers)
    assert page_two.status_code == 200
    assert len(page_two.json()["items"]) == 1


def test_download_import_template(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    response = client.get(
        f"/api/v1/fc-projects/{project_id}/experience-cases/import-template",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(response.content) > 0

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.fc_generation_batch import FcGenerationBatch, FcGenerationBatchStatus
from app.models.user import User


def _create_fc_project(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/fc-projects",
        headers=auth_headers,
        json={"name": "Case Project", "description": "For functional cases"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _upload_requirement_doc(
    client: TestClient,
    auth_headers: dict[str, str],
    project_id: str,
) -> str:
    response = client.post(
        f"/api/v1/fc-projects/{project_id}/docs/upload",
        headers=auth_headers,
        files={"file": ("requirements.txt", b"Login module requirement", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["doc"]["id"]


@pytest.fixture
def db_session(migrated_db: str) -> Generator[Session, None, None]:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_fc_test_case_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/cases"

    create_response = client.post(
        base_url,
        headers=auth_headers,
        json={
            "case_no": "FC-001",
            "module": "用户登录",
            "title": "正确密码登录",
            "preconditions": "用户已注册",
            "steps": "1. 输入账号\n2. 点击登录",
            "expected_result": "登录成功",
            "priority": "P0",
            "case_type": "positive",
            "status": "draft",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    case_id = created["id"]
    assert created["case_no"] == "FC-001"
    assert created["status"] == "draft"

    list_response = client.get(f"{base_url}?status=draft", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = client.get(f"{base_url}/{case_id}", headers=auth_headers)
    assert get_response.status_code == 200

    update_response = client.put(
        f"{base_url}/{case_id}",
        headers=auth_headers,
        json={"title": "更新后的标题", "status": "active"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "更新后的标题"
    assert update_response.json()["status"] == "active"

    delete_response = client.delete(f"{base_url}/{case_id}", headers=auth_headers)
    assert delete_response.status_code == 204


def test_fc_test_case_auto_case_no(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/cases"

    response = client.post(
        base_url,
        headers=auth_headers,
        json={
            "module": "订单",
            "title": "创建订单",
            "steps": "1. 提交订单",
            "expected_result": "创建成功",
        },
    )
    assert response.status_code == 201
    assert response.json()["case_no"] == "FC-001"


def _create_case(
    client: TestClient,
    auth_headers: dict[str, str],
    project_id: str,
    *,
    title: str,
    status: str = "active",
) -> str:
    response = client.post(
        f"/api/v1/fc-projects/{project_id}/cases",
        headers=auth_headers,
        json={
            "module": "用户登录",
            "title": title,
            "steps": "1. 操作",
            "expected_result": "成功",
            "status": status,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_fc_test_case_batch_delete(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/cases"
    case_a = _create_case(client, auth_headers, project_id, title="用例 A")
    case_b = _create_case(client, auth_headers, project_id, title="用例 B")

    response = client.post(
        f"{base_url}/batch-delete",
        headers=auth_headers,
        json={"case_ids": [case_a, case_b]},
    )
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2

    list_response = client.get(f"{base_url}?status=active", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_fc_test_case_batch_delete_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    response = client.post(
        f"/api/v1/fc-projects/{project_id}/cases/batch-delete",
        headers=auth_headers,
        json={"case_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 404


def test_fc_test_case_list_pagination(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    base_url = f"/api/v1/fc-projects/{project_id}/cases"

    for index in range(3):
        _create_case(client, auth_headers, project_id, title=f"用例 {index}")

    page_one = client.get(f"{base_url}?status=active&page=1&page_size=2", headers=auth_headers)
    assert page_one.status_code == 200
    data = page_one.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2

    page_two = client.get(f"{base_url}?status=active&page=2&page_size=2", headers=auth_headers)
    assert page_two.status_code == 200
    assert len(page_two.json()["items"]) == 1


def test_fc_test_case_filter_options(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_fc_project(client, auth_headers)
    case_a = _create_case(client, auth_headers, project_id, title="用例 A")
    _create_case(client, auth_headers, project_id, title="用例 B")

    update_response = client.put(
        f"/api/v1/fc-projects/{project_id}/cases/{case_a}",
        headers=auth_headers,
        json={"module": "订单模块"},
    )
    assert update_response.status_code == 200

    response = client.get(
        f"/api/v1/fc-projects/{project_id}/cases/filter-options?status=active",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert "用户登录" in payload["modules"]
    assert "订单模块" in payload["modules"]


def test_generation_batch_read_only_api(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    from sqlalchemy import select

    project_id = _create_fc_project(client, auth_headers)
    doc_id = uuid.UUID(_upload_requirement_doc(client, auth_headers, project_id))

    triggered_by = db_session.scalar(select(User).limit(1))
    assert triggered_by is not None

    batch = FcGenerationBatch(
        fc_project_id=uuid.UUID(project_id),
        requirement_doc_id=doc_id,
        experience_case_ids=[],
        status=FcGenerationBatchStatus.AWAITING_REVIEW.value,
        coverage_score=85.5,
        review_report_json={"passed": True},
        internal_retry_count=1,
        triggered_by=triggered_by.id,
    )
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)

    list_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    batches = list_response.json()
    assert len(batches) == 1
    assert batches[0]["coverage_score"] == 85.5
    assert batches[0]["status"] == "awaiting_review"

    detail_response = client.get(
        f"/api/v1/fc-projects/{project_id}/batches/{batch.id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == str(batch.id)

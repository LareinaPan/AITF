import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.models.pt_run import PtRun, PtRunStatus
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.services.pt_load_engine import LoadSampleResult
from app.services.pt_metrics_aggregator import PtMetricsAggregator

DEMO_JMX = Path(__file__).resolve().parents[2] / "docs" / "demo" / "demo-load-test.jmx"


def _create_project_and_scenario(client: TestClient, auth_headers: dict[str, str]) -> tuple[str, str]:
    project_response = client.post(
        "/api/v1/pt-projects",
        headers=auth_headers,
        json={"name": "Run API Project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    scenario_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios",
        headers=auth_headers,
        json={"name": "Run API Scenario"},
    )
    assert scenario_response.status_code == 201
    scenario_id = scenario_response.json()["id"]
    return project_id, scenario_id


def _prepare_runnable_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
) -> tuple[str, str]:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)
    upload_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/upload",
        headers=auth_headers,
        files={"file": ("demo-load-test.jmx", DEMO_JMX.read_bytes(), "application/xml")},
    )
    assert upload_response.status_code == 201

    config_response = client.put(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/script/config",
        headers=auth_headers,
        json={
            "max_concurrency": 2,
            "ramp_up_seconds": 0,
            "stop_mode": "duration",
            "duration_seconds": 30,
        },
    )
    assert config_response.status_code == 200
    return project_id, scenario_id


def _create_running_run(
    client: TestClient,
    auth_headers: dict[str, str],
) -> tuple[str, str]:
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)
    with patch("app.api.pt_runs.schedule_load_test"):
        run_response = client.post(
            f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
            headers=auth_headers,
        )
    assert run_response.status_code == 201
    return project_id, run_response.json()["run_id"]


def _seed_completed_run_with_query_data(
    client: TestClient,
    auth_headers: dict[str, str],
) -> tuple[str, str]:
    from app.database import SessionLocal

    project_id, run_id = _create_running_run(client, auth_headers)
    started_at = datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(seconds=30)

    with SessionLocal() as db:
        run = db.get(PtRun, uuid.UUID(run_id))
        assert run is not None
        run.status = PtRunStatus.COMPLETED.value
        run.stop_reason = "duration_reached"
        run.started_at = started_at
        run.ended_at = ended_at
        run.summary_json = {
            "run_id": run_id,
            "status": "completed",
            "stop_reason": "duration_reached",
            "interfaces": [
                {
                    "sampler_key": "sampler-001",
                    "name": "List Users",
                    "rt_p99_ms": 95.0,
                    "rt_p95_ms": 80.0,
                    "qps": 1.5,
                    "error_rate_percent": 0.0,
                    "total_requests": 45,
                    "failed_requests": 0,
                }
            ],
        }
        db.add(
            PtRunMetricPoint(
                pt_run_id=run.id,
                sampler_key="sampler-001",
                recorded_at=started_at + timedelta(seconds=3),
                qps=10.0,
                avg_rt_ms=50.0,
                rt_p95_ms=80.0,
                rt_p99_ms=95.0,
                error_rate_percent=0.0,
            )
        )
        db.add(
            PtRunMetricPoint(
                pt_run_id=run.id,
                sampler_key="sampler-001",
                recorded_at=started_at + timedelta(seconds=6),
                qps=12.0,
                avg_rt_ms=55.0,
                rt_p95_ms=85.0,
                rt_p99_ms=98.0,
                error_rate_percent=0.0,
            )
        )
        for index in range(3):
            db.add(
                PtRunErrorLog(
                    pt_run_id=run.id,
                    occurred_at=started_at + timedelta(seconds=index + 1),
                    sampler_key="sampler-001",
                    sampler_name="List Users",
                    status_code=500,
                    error_type="http_error",
                    message=f"HTTP 500 #{index}",
                )
            )
        db.commit()

    return project_id, run_id


@patch("app.api.pt_runs.schedule_load_test")
def test_start_pt_run_success(
    mock_schedule_load_test,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
        headers=auth_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["run_id"]
    mock_schedule_load_test.assert_called_once()


def test_start_pt_run_rejects_unparsed_script(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id = _create_project_and_scenario(client, auth_headers)

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
        headers=auth_headers,
    )
    assert response.status_code == 400


@patch("app.api.pt_runs.schedule_load_test")
def test_start_pt_run_conflict_when_running_exists(
    mock_schedule_load_test,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)

    first_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
        headers=auth_headers,
    )
    assert first_response.status_code == 201

    second_response = client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
        headers=auth_headers,
    )
    assert second_response.status_code == 409


@patch("app.api.pt_runs.cancel_load_test", new_callable=AsyncMock)
def test_cancel_pt_run_success(
    mock_cancel_load_test,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    mock_cancel_load_test.return_value = None
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)

    with patch("app.api.pt_runs.schedule_load_test"):
        run_response = client.post(
            f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
            headers=auth_headers,
        )
    run_id = run_response.json()["run_id"]

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["run_id"] == run_id

    from app.database import SessionLocal
    from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason

    with SessionLocal() as db:
        run = db.get(PtRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == PtRunStatus.CANCELLED.value
        assert run.stop_reason == PtRunStopReason.MANUAL_CANCEL.value
        assert run.ended_at is not None


@patch("app.api.pt_runs.cancel_load_test", new_callable=AsyncMock)
def test_cancel_pt_run_persists_when_engine_already_gone(
    mock_cancel_load_test,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    from app.services.pt_run_orchestrator import PtRunNotRunningError

    mock_cancel_load_test.side_effect = PtRunNotRunningError("not active")
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)

    with patch("app.api.pt_runs.schedule_load_test"):
        run_response = client.post(
            f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
            headers=auth_headers,
        )
    run_id = run_response.json()["run_id"]

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    from app.database import SessionLocal
    from app.models.pt_run import PtRun, PtRunStatus

    with SessionLocal() as db:
        run = db.get(PtRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == PtRunStatus.CANCELLED.value


def test_cancel_pt_run_conflict_when_not_running(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, scenario_id = _prepare_runnable_scenario(client, auth_headers)

    with patch("app.api.pt_runs.schedule_load_test"):
        run_response = client.post(
            f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
            headers=auth_headers,
        )
    run_id = run_response.json()["run_id"]

    from app.database import SessionLocal
    from app.models.pt_run import PtRun, PtRunStatus

    with SessionLocal() as db:
        run = db.get(PtRun, uuid.UUID(run_id))
        assert run is not None
        run.status = PtRunStatus.COMPLETED.value
        db.commit()

    response = client.post(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_list_pt_runs(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _seed_completed_run_with_query_data(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == run_id
    assert payload["items"][0]["status"] == "completed"


def test_list_pt_runs_filter_by_status(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, _ = _seed_completed_run_with_query_data(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs",
        headers=auth_headers,
        params={"status": "running"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_pt_run_detail_with_summary(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _seed_completed_run_with_query_data(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["summary_json"]["interfaces"][0]["sampler_key"] == "sampler-001"
    assert payload["config_snapshot_json"]["max_concurrency"] == 2


def test_get_pt_run_detail_interim_summary_when_running(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _create_running_run(client, auth_headers)
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)
    aggregator.record(
        LoadSampleResult(
            sampler_key="sampler-001",
            sampler_name="List Users",
            status_code=200,
            response_time_ms=100.0,
            success=True,
            error_type=None,
            message=None,
            occurred_at=datetime.now(timezone.utc),
        )
    )

    with patch("app.api.pt_runs.get_run_aggregator", return_value=aggregator):
        response = client.get(
            f"/api/v1/pt-projects/{project_id}/runs/{run_id}",
            headers=auth_headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["summary_json"]["status"] == "running"
    assert payload["summary_json"]["interfaces"][0]["total_requests"] == 1


def test_get_pt_run_metrics_with_since_filter(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _seed_completed_run_with_query_data(client, auth_headers)
    since = "2026-07-03T10:00:05Z"

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/metrics",
        headers=auth_headers,
        params={"sampler_key": "sampler-001", "since": since},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["qps"] == 12.0


def test_get_pt_run_errors_latest(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _seed_completed_run_with_query_data(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
        headers=auth_headers,
        params={"latest": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["total"] is None
    assert payload["items"][0]["message"] == "HTTP 500 #2"


def test_get_pt_run_errors_paginated(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, run_id = _seed_completed_run_with_query_data(client, auth_headers)

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
        headers=auth_headers,
        params={"page": 1, "page_size": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2
    assert payload["page"] == 1


def test_get_pt_run_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id, _ = _create_project_and_scenario(client, auth_headers)
    missing_run_id = uuid.uuid4()

    assert client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{missing_run_id}",
        headers=auth_headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{missing_run_id}/metrics",
        headers=auth_headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{missing_run_id}/errors",
        headers=auth_headers,
    ).status_code == 404


def test_pt_run_endpoints_require_auth(client: TestClient) -> None:
    project_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    run_id = uuid.uuid4()

    assert client.get(f"/api/v1/pt-projects/{project_id}/runs").status_code == 403
    assert client.get(f"/api/v1/pt-projects/{project_id}/runs/{run_id}").status_code == 403
    assert client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/metrics",
    ).status_code == 403
    assert client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
    ).status_code == 403
    assert client.post(
        f"/api/v1/pt-projects/{project_id}/scenarios/{scenario_id}/run",
    ).status_code == 403
    assert client.post(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/cancel",
    ).status_code == 403


def test_get_pt_run_errors_sanitizes_unredacted_db_message(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    from app.database import SessionLocal

    project_id, run_id = _create_running_run(client, auth_headers)

    with SessionLocal() as db:
        run = db.get(PtRun, uuid.UUID(run_id))
        assert run is not None
        db.add(
            PtRunErrorLog(
                pt_run_id=run.id,
                occurred_at=datetime.now(timezone.utc),
                sampler_key="sampler-001",
                sampler_name="List Users",
                status_code=401,
                error_type="http_error",
                message="Authorization: Bearer leaked-token",
            )
        )
        db.commit()

    response = client.get(
        f"/api/v1/pt-projects/{project_id}/runs/{run_id}/errors",
        headers=auth_headers,
        params={"latest": 1},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["message"] == "Authorization: ***"

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import get_settings

from app.services.allure_service import (
    AllureReportWriter,
    generate_allure_report,
    get_reports_dir,
    get_results_dir,
    resolve_allure_cli,
)
from app.services.test_runner import (
    HttpResponseSnapshot,
    PlanRunCaseResult,
    PlanRunResult,
    PreparedRequest,
    SingleRunResult,
)


def _sample_plan_result() -> PlanRunResult:
    case_id = uuid.uuid4()
    single = SingleRunResult(
        case_id=case_id,
        case_name="Demo Case",
        environment_id=uuid.uuid4(),
        environment_name="dev",
        prepared_request=PreparedRequest(
            method="GET",
            url="http://localhost/api",
            headers={},
            params={},
            body_type="none",
            body_content="",
        ),
        assertions_json={"status_code": 200, "max_response_time_ms": 3000, "body_rules": []},
        passed=True,
        response=HttpResponseSnapshot(status_code=200, body='{"ok":true}', elapsed_ms=12.0),
        assertions=None,
        error=None,
    )
    return PlanRunResult(
        plan_id=uuid.uuid4(),
        plan_name="Smoke",
        environment_id=uuid.uuid4(),
        environment_name="dev",
        trigger="manual",
        total_count=1,
        pass_count=1,
        fail_count=0,
        passed=True,
        case_results=[
            PlanRunCaseResult(
                case_id=case_id,
                case_name="Demo Case",
                sort_order=0,
                passed=True,
                result=single,
            )
        ],
    )


def test_allure_writer_creates_result_files(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")

    run_id = uuid.uuid4()
    writer = AllureReportWriter(run_id, plan_name="Smoke")
    summary = writer.write_plan_result(_sample_plan_result())

    assert summary.result_files == 1
    result_files = list(get_results_dir(run_id).glob("*-result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["name"] == "Demo Case"
    assert payload["status"] == "passed"


def test_generate_allure_report_fallback_html(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.allure_service.ALLURE_RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("app.services.allure_service.ALLURE_REPORTS_DIR", tmp_path / "reports")

    run_id = uuid.uuid4()
    writer = AllureReportWriter(run_id, plan_name="Smoke")
    writer.write_plan_result(_sample_plan_result())

    with patch("app.services.allure_service.resolve_allure_cli", return_value=None):
        reports_dir = generate_allure_report(run_id)

    index_html = reports_dir / "index.html"
    assert index_html.exists()
    assert "Demo Case" in index_html.read_text(encoding="utf-8")


def test_resolve_allure_cli_uses_configured_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_path = tmp_path / "allure"
    cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
    cli_path.chmod(0o755)

    monkeypatch.setenv("ALLURE_CLI", str(cli_path))
    get_settings.cache_clear()

    assert resolve_allure_cli() == str(cli_path)

    get_settings.cache_clear()

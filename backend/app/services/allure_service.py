import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from html import escape
from pathlib import Path

from app.config import STORAGE_DIR, get_settings
from app.services.test_runner import PlanRunCaseResult, PlanRunResult

ALLURE_RESULTS_DIR = STORAGE_DIR / "allure-results"
ALLURE_REPORTS_DIR = STORAGE_DIR / "allure-reports"

logger = logging.getLogger(__name__)


def ensure_storage_dirs() -> None:
    ALLURE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ALLURE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_results_dir(run_id: uuid.UUID) -> Path:
    return ALLURE_RESULTS_DIR / str(run_id)


def get_reports_dir(run_id: uuid.UUID) -> Path:
    return ALLURE_REPORTS_DIR / str(run_id)


def build_report_url(run_id: uuid.UUID) -> str:
    base = get_settings().report_base_url.rstrip("/")
    return f"{base}/{run_id}/index.html"


def resolve_allure_cli() -> str | None:
    """Return executable path for Allure CLI, or None if unavailable."""
    configured = get_settings().allure_cli.strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
    return shutil.which("allure")


@dataclass(frozen=True)
class AllureWriteSummary:
    run_id: uuid.UUID
    result_files: int


class AllureReportWriter:
    """Write Allure 2 result JSON files for a plan run."""

    def __init__(self, run_id: uuid.UUID, *, plan_name: str) -> None:
        ensure_storage_dirs()
        self.run_id = run_id
        self.plan_name = plan_name
        self.results_dir = get_results_dir(run_id)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._result_files = 0

    def write_plan_result(self, plan_result: PlanRunResult) -> AllureWriteSummary:
        for case_result in plan_result.case_results:
            self._write_case_result(case_result)
        return AllureWriteSummary(run_id=self.run_id, result_files=self._result_files)

    def _write_case_result(self, case_result: PlanRunCaseResult) -> None:
        result_uuid = str(uuid.uuid4())
        started = int(time.time() * 1000)
        stopped = started + 1
        single = case_result.result

        attachments: list[dict[str, str]] = []
        steps: list[dict[str, object]] = []

        request_attachment = self._write_attachment(
            result_uuid,
            "request.txt",
            self._format_request(single.prepared_request),
        )
        attachments.append(request_attachment)
        steps.append(
            {
                "name": "HTTP Request",
                "status": "passed",
                "stage": "finished",
                "start": started,
                "stop": stopped,
                "attachments": [request_attachment],
            }
        )

        if single.response is not None:
            response_attachment = self._write_attachment(
                result_uuid,
                "response.txt",
                self._format_response(single.response.status_code, single.response.body),
            )
            attachments.append(response_attachment)
            steps.append(
                {
                    "name": "HTTP Response",
                    "status": "passed" if case_result.passed else "failed",
                    "stage": "finished",
                    "start": started,
                    "stop": stopped,
                    "attachments": [response_attachment],
                }
            )

        if single.assertions is not None:
            assertion_lines = [
                f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.message}"
                for check in single.assertions.checks
            ]
            assertion_attachment = self._write_attachment(
                result_uuid,
                "assertions.txt",
                "\n".join(assertion_lines) or "No assertion checks",
            )
            attachments.append(assertion_attachment)
            steps.append(
                {
                    "name": "Assertions",
                    "status": "passed" if single.assertions.passed else "failed",
                    "stage": "finished",
                    "start": started,
                    "stop": stopped,
                    "attachments": [assertion_attachment],
                }
            )

        status = "passed" if case_result.passed else "failed"
        status_details: dict[str, str] = {}
        if single.error:
            status = "broken"
            status_details = {"message": single.error}
        elif not case_result.passed:
            status_details = {"message": "Assertion checks failed"}

        payload = {
            "uuid": result_uuid,
            "historyId": str(case_result.case_id),
            "name": case_result.case_name,
            "fullName": f"{self.plan_name}#{case_result.sort_order + 1:03d}",
            "status": status,
            "statusDetails": status_details,
            "stage": "finished",
            "start": started,
            "stop": stopped,
            "steps": steps,
            "attachments": attachments,
            "labels": [
                {"name": "suite", "value": self.plan_name},
                {"name": "parentSuite", "value": "AITF Test Plan"},
            ],
        }

        result_path = self.results_dir / f"{result_uuid}-result.json"
        result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self._result_files += 1

    def _write_attachment(self, result_uuid: str, filename: str, content: str) -> dict[str, str]:
        attachment_uuid = str(uuid.uuid4())
        attachment_path = self.results_dir / f"{attachment_uuid}-attachment.txt"
        attachment_path.write_text(content, encoding="utf-8")
        return {
            "name": filename,
            "source": f"{attachment_uuid}-attachment.txt",
            "type": "text/plain",
        }

    @staticmethod
    def _format_request(prepared) -> str:
        lines = [
            f"{prepared.method} {prepared.url}",
            "",
            "Headers:",
        ]
        for key, value in prepared.headers.items():
            lines.append(f"  {key}: {value}")
        if prepared.params:
            lines.extend(["", "Query:", *[f"  {k}={v}" for k, v in prepared.params.items()]])
        if prepared.body_type != "none":
            lines.extend(["", f"Body ({prepared.body_type}):", prepared.body_content])
        return "\n".join(lines)

    @staticmethod
    def _format_response(status_code: int, body: str) -> str:
        return f"Status: {status_code}\n\n{body}"


def generate_allure_report(run_id: uuid.UUID) -> Path:
    ensure_storage_dirs()
    results_dir = get_results_dir(run_id)
    reports_dir = get_reports_dir(run_id)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not any(results_dir.iterdir()):
        _generate_fallback_html(reports_dir, run_id, [])
        return reports_dir

    allure_cli = resolve_allure_cli()
    if allure_cli is None:
        logger.warning("Allure CLI not found; using fallback HTML for run %s", run_id)
        summaries = _load_result_summaries(results_dir)
        _generate_fallback_html(reports_dir, run_id, summaries)
        return reports_dir

    try:
        completed = subprocess.run(
            [
                allure_cli,
                "generate",
                str(results_dir),
                "-o",
                str(reports_dir),
                "--clean",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "ALLURE_NO_ANALYTICS": "1"},
        )
        logger.info("Allure report generated for run %s", run_id)
        if completed.stderr:
            logger.debug("allure generate stderr: %s", completed.stderr.strip())
    except FileNotFoundError:
        logger.warning("Allure CLI not found; using fallback HTML for run %s", run_id)
        summaries = _load_result_summaries(results_dir)
        _generate_fallback_html(reports_dir, run_id, summaries)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Allure generate failed for run %s (exit %s): %s",
            run_id,
            exc.returncode,
            (exc.stderr or exc.stdout or "").strip(),
        )
        summaries = _load_result_summaries(results_dir)
        _generate_fallback_html(reports_dir, run_id, summaries)

    return reports_dir


def _load_result_summaries(results_dir: Path) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for path in sorted(results_dir.glob("*-result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        summaries.append(
            {
                "name": str(data.get("name", path.stem)),
                "status": str(data.get("status", "unknown")),
            }
        )
    return summaries


def _generate_fallback_html(
    reports_dir: Path,
    run_id: uuid.UUID,
    summaries: list[dict[str, str]],
) -> None:
    rows = "".join(
        (
            f"<tr><td>{escape(item['name'])}</td>"
            f"<td>{escape(item['status'])}</td></tr>"
        )
        for item in summaries
    )
    if not rows:
        rows = "<tr><td colspan='2'>No test results</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>AITF Report {run_id}</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>AITF Test Plan Report</h1>
  <p>Run ID: {escape(str(run_id))}</p>
  <p><em>Allure CLI unavailable — showing fallback summary.</em></p>
  <table>
    <thead><tr><th>Case</th><th>Status</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    (reports_dir / "index.html").write_text(html, encoding="utf-8")

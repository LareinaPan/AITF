import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.project import Project
from app.models.test_plan import PlanRun, TestPlan
from app.services.allure_service import AllureReportWriter, build_report_url, generate_allure_report
from app.services.feishu_notifier import FeishuNotificationError, notify_plan_run_completed
from app.services.test_runner import PlanRunResult, TestPlanNotFoundError, TestRunner

logger = logging.getLogger(__name__)


class PlanExecutionError(RuntimeError):
    """Raised when plan execution fails unexpectedly."""


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _send_plan_run_notification(
    db: Session,
    *,
    plan: TestPlan,
    plan_result: PlanRunResult,
    finished_at: datetime,
    report_url: str | None,
) -> None:
    db.refresh(plan)
    project = db.get(Project, plan.project_id)
    if project is None:
        logger.warning("Skip Feishu notification: project not found for plan %s", plan.id)
        return
    if not plan.notify_on_complete:
        logger.info("Skip Feishu notification: disabled for plan %s", plan.id)
        return
    if not project.feishu_webhook_url or not project.feishu_webhook_url.strip():
        logger.warning(
            "Skip Feishu notification: webhook not configured for project %s",
            project.id,
        )
        return

    try:
        notify_plan_run_completed(
            webhook_url=project.feishu_webhook_url,
            project_name=project.name,
            plan_name=plan_result.plan_name,
            executed_at=_ensure_utc(finished_at),
            pass_count=plan_result.pass_count,
            fail_count=plan_result.fail_count,
            total_count=plan_result.total_count,
            report_url=report_url,
        )
        logger.info("Feishu notification sent for plan %s", plan.id)
    except FeishuNotificationError as exc:
        logger.warning("Feishu notification failed for plan %s: %s", plan.id, exc)
    except Exception:
        logger.exception("Unexpected error sending Feishu notification for plan %s", plan.id)


def execute_test_plan(
    db: Session,
    plan_id: uuid.UUID,
    *,
    trigger: str = "manual",
) -> tuple[PlanRun, PlanRunResult]:
    plan = db.scalar(
        select(TestPlan)
        .where(TestPlan.id == plan_id)
        .options(selectinload(TestPlan.project))
    )
    if plan is None:
        raise TestPlanNotFoundError(f"Test plan not found: {plan_id}")

    plan_run = PlanRun(
        plan_id=plan.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(plan_run)
    db.commit()
    db.refresh(plan_run)

    runner = TestRunner(db)
    try:
        plan_result = runner.run_plan(plan.id, trigger=trigger)
    except Exception as exc:
        plan_run.status = "failed"
        plan_run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise PlanExecutionError(str(exc)) from exc

    writer = AllureReportWriter(plan_run.id, plan_name=plan_result.plan_name)
    writer.write_plan_result(plan_result)
    generate_allure_report(plan_run.id)
    report_url = build_report_url(plan_run.id)

    plan_run.status = "completed" if plan_result.passed else "failed"
    plan_run.total_count = plan_result.total_count
    plan_run.pass_count = plan_result.pass_count
    plan_run.fail_count = plan_result.fail_count
    plan_run.allure_report_url = report_url
    plan_run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan_run)

    _send_plan_run_notification(
        db,
        plan=plan,
        plan_result=plan_result,
        finished_at=plan_run.finished_at,
        report_url=report_url,
    )

    return plan_run, plan_result

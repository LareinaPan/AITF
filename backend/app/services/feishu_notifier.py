from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.config import get_settings

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class FeishuNotificationError(RuntimeError):
    """Raised when Feishu webhook delivery fails."""


def build_plan_report_message(
    *,
    project_name: str,
    plan_name: str,
    executed_at: datetime,
    pass_count: int,
    fail_count: int,
    total_count: int,
    report_url: str | None,
) -> str:
    executed_label = executed_at.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    report_line = report_url or "（报告生成失败）"
    return (
        "【AITF 测试报告】\n"
        f"项目：{project_name}\n"
        f"计划：{plan_name}\n"
        f"时间：{executed_label}\n"
        f"结果：通过 {pass_count}/{total_count}，失败 {fail_count}\n"
        f"报告：{report_line}"
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
def _post_webhook(webhook_url: str, payload: dict[str, object]) -> None:
    timeout = get_settings().feishu_webhook_timeout_seconds
    with httpx.Client(timeout=timeout) as client:
        response = client.post(webhook_url, json=payload)
        response.raise_for_status()
        _validate_feishu_response(response)


def _validate_feishu_response(response: httpx.Response) -> None:
    try:
        body = response.json()
    except ValueError as exc:
        raise FeishuNotificationError(f"Invalid Feishu response JSON: {exc}") from exc

    if not isinstance(body, dict):
        raise FeishuNotificationError("Invalid Feishu response payload")

    status_code = body.get("StatusCode", body.get("code"))
    if status_code not in (0, "0", None):
        message = body.get("StatusMessage") or body.get("msg") or "unknown error"
        raise FeishuNotificationError(f"Feishu webhook rejected message: {message}")


def send_feishu_text_message(webhook_url: str, text: str) -> None:
    if not webhook_url.strip():
        return

    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    try:
        _post_webhook(webhook_url.strip(), payload)
    except RetryError as exc:
        cause = exc.last_attempt.exception()
        raise FeishuNotificationError(
            f"Feishu webhook request failed after retries: {cause}"
        ) from cause
    except httpx.HTTPError as exc:
        raise FeishuNotificationError(f"Feishu webhook request failed: {exc}") from exc


def notify_plan_run_completed(
    *,
    webhook_url: str | None,
    project_name: str,
    plan_name: str,
    executed_at: datetime,
    pass_count: int,
    fail_count: int,
    total_count: int,
    report_url: str | None,
) -> None:
    if not webhook_url:
        return

    message = build_plan_report_message(
        project_name=project_name,
        plan_name=plan_name,
        executed_at=executed_at,
        pass_count=pass_count,
        fail_count=fail_count,
        total_count=total_count,
        report_url=report_url,
    )
    send_feishu_text_message(webhook_url, message)

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.feishu_notifier import (
    FeishuNotificationError,
    build_plan_report_message,
    notify_plan_run_completed,
    send_feishu_text_message,
)


def test_build_plan_report_message_contains_summary() -> None:
    message = build_plan_report_message(
        project_name="Demo",
        plan_name="Smoke",
        executed_at=datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc),
        pass_count=2,
        fail_count=1,
        total_count=3,
        report_url="http://localhost:8000/reports/run/index.html",
    )
    assert "Demo" in message
    assert "Smoke" in message
    assert "通过 2/3" in message
    assert "失败 1" in message
    assert "2026-06-22 17:00:00" in message
    assert "UTC" not in message
    assert "http://localhost:8000/reports/run/index.html" in message


@patch("app.services.feishu_notifier.httpx.Client")
def test_send_feishu_text_message_posts_payload(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"StatusCode": 0, "msg": "success"}
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    send_feishu_text_message("https://example.com/hook", "hello")

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "https://example.com/hook"
    assert kwargs["json"]["msg_type"] == "text"
    assert kwargs["json"]["content"]["text"] == "hello"


@patch("app.services.feishu_notifier.httpx.Client")
def test_send_feishu_text_message_raises_on_http_error(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = httpx.ConnectError("down")
    mock_client_cls.return_value = mock_client

    with pytest.raises(FeishuNotificationError):
        send_feishu_text_message("https://example.com/hook", "hello")


@patch("app.services.feishu_notifier.httpx.Client")
def test_send_feishu_text_message_raises_on_business_error(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"StatusCode": 19021, "StatusMessage": "sign match fail"}
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    with pytest.raises(FeishuNotificationError, match="rejected message"):
        send_feishu_text_message("https://example.com/hook", "hello")


def test_notify_plan_run_completed_skips_without_webhook() -> None:
    notify_plan_run_completed(
        webhook_url=None,
        project_name="Demo",
        plan_name="Smoke",
        executed_at=datetime.now(timezone.utc),
        pass_count=1,
        fail_count=0,
        total_count=1,
        report_url="http://localhost/report",
    )

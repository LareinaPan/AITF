import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.cron_validator import (
    CronExpressionError,
    build_plan_cron_trigger,
    convert_unix_day_of_week_field,
    normalize_cron_expression,
    validate_enabled_cron,
)


def test_normalize_cron_expression_accepts_valid_five_field_cron() -> None:
    assert normalize_cron_expression("0 9 * * *") == "0 9 * * *"
    assert normalize_cron_expression("  0 2 * * *  ") == "0 2 * * *"


def test_normalize_cron_expression_allows_empty() -> None:
    assert normalize_cron_expression(None) is None
    assert normalize_cron_expression("") is None
    assert normalize_cron_expression("   ") is None


def test_normalize_cron_expression_rejects_invalid() -> None:
    with pytest.raises(CronExpressionError, match="Invalid cron expression"):
        normalize_cron_expression("not a cron")

    with pytest.raises(CronExpressionError):
        normalize_cron_expression("* * *")


def test_validate_enabled_cron_requires_expression_when_enabled() -> None:
    validate_enabled_cron(is_enabled=False, cron_expression=None)
    validate_enabled_cron(is_enabled=True, cron_expression="0 9 * * *")

    with pytest.raises(CronExpressionError, match="required"):
        validate_enabled_cron(is_enabled=True, cron_expression=None)


def test_convert_unix_day_of_week_field_maps_weekdays() -> None:
    assert convert_unix_day_of_week_field("*") == "*"
    assert convert_unix_day_of_week_field("1-5") == "0-4"
    assert convert_unix_day_of_week_field("0") == "6"
    assert convert_unix_day_of_week_field("1,3,5") == "0,2,4"


def test_build_plan_cron_trigger_fires_on_monday_beijing_time() -> None:
    trigger = build_plan_cron_trigger("50 10 * * 1-5")
    monday = datetime(2026, 6, 22, 10, 49, tzinfo=ZoneInfo("Asia/Shanghai"))
    next_fire = trigger.get_next_fire_time(None, monday)
    assert next_fire == datetime(2026, 6, 22, 10, 50, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_build_plan_cron_trigger_skips_weekend() -> None:
    trigger = build_plan_cron_trigger("50 10 * * 1-5")
    saturday = datetime(2026, 6, 27, 10, 49, tzinfo=ZoneInfo("Asia/Shanghai"))
    next_fire = trigger.get_next_fire_time(None, saturday)
    assert next_fire == datetime(2026, 6, 29, 10, 50, tzinfo=ZoneInfo("Asia/Shanghai"))

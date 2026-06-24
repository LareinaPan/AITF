import re

from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

from app.config import get_settings


class CronExpressionError(ValueError):
    """Raised when a cron expression is invalid."""


def normalize_cron_expression(expression: str | None) -> str | None:
    if expression is None:
        return None

    stripped = expression.strip()
    if not stripped:
        return None

    if not croniter.is_valid(stripped):
        raise CronExpressionError(
            f"Invalid cron expression: {stripped!r}. "
            "Use 5-field format, e.g. 0 9 * * * (minute hour day month weekday).",
        )

    return stripped


def validate_enabled_cron(
    *,
    is_enabled: bool,
    cron_expression: str | None,
) -> None:
    if is_enabled and not cron_expression:
        raise CronExpressionError(
            "Cron expression is required when scheduled execution is enabled",
        )


def _unix_weekday_to_apscheduler(value: int) -> int:
    """Convert Unix cron weekday (0/7=Sunday) to APScheduler weekday (0=Monday)."""
    normalized = value % 7
    if normalized == 0:
        return 6
    return normalized - 1


def _convert_unix_day_of_week_token(token: str) -> str:
    token = token.strip()
    if not token or token == "*":
        return token

    if re.search(r"[a-zA-Z]", token):
        return token.lower()

    if "/" in token:
        base, step = token.split("/", 1)
        return f"{_convert_unix_day_of_week_token(base)}/{step}"

    if "-" in token:
        start, end = token.split("-", 1)
        if start.isdigit() and end.isdigit():
            converted_start = _unix_weekday_to_apscheduler(int(start))
            converted_end = _unix_weekday_to_apscheduler(int(end))
            return f"{converted_start}-{converted_end}"
        return token.lower()

    if token.isdigit():
        return str(_unix_weekday_to_apscheduler(int(token)))

    return token


def convert_unix_day_of_week_field(day_of_week: str) -> str:
    """Convert Unix-style weekday field for APScheduler (0=Monday)."""
    return ",".join(_convert_unix_day_of_week_token(part) for part in day_of_week.split(","))


def build_plan_cron_trigger(cron_expression: str) -> CronTrigger:
    """Build APScheduler trigger from a Unix 5-field cron expression."""
    parts = cron_expression.split()
    if len(parts) != 5:
        raise CronExpressionError(
            f"Invalid cron expression: {cron_expression!r}. "
            "Use 5-field format, e.g. 0 9 * * * (minute hour day month weekday).",
        )

    minute, hour, day, month, day_of_week = parts
    settings = get_settings()
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=convert_unix_day_of_week_field(day_of_week),
        timezone=settings.scheduler_timezone,
    )

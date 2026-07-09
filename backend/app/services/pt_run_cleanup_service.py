"""Cleanup expired performance test run records and related rows."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.pt_run import PtRun

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PtRunCleanupSummary:
    deleted_runs: int


def cleanup_expired_pt_runs(
    db: Session,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> PtRunCleanupSummary:
    """Delete PtRun rows older than the retention window (by ``started_at``)."""
    days = retention_days if retention_days is not None else get_settings().pt_run_retention_days
    reference_time = now or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    cutoff = reference_time - timedelta(days=days)

    expired_runs = list(
        db.scalars(
            select(PtRun)
            .where(PtRun.started_at < cutoff)
            .order_by(PtRun.started_at),
        ).all(),
    )

    for run in expired_runs:
        db.delete(run)

    if expired_runs:
        db.commit()
        logger.info(
            "PT run cleanup removed %s run(s) older than %s days",
            len(expired_runs),
            days,
        )

    return PtRunCleanupSummary(deleted_runs=len(expired_runs))


def delete_pt_run(db: Session, run_id: uuid.UUID) -> bool:
    run = db.get(PtRun, run_id)
    if run is None:
        return False
    db.delete(run)
    db.commit()
    return True

"""Recover orphaned performance test runs after process restart."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason

logger = logging.getLogger(__name__)

ORPHAN_ERROR_MESSAGE = "Load test interrupted by server restart"


def recover_orphaned_running_runs(db: Session | None = None) -> int:
    """Mark all ``running`` PtRun rows as ``failed`` on application startup."""
    owns_session = db is None
    session = db or database.SessionLocal()
    try:
        runs = list(
            session.scalars(
                select(PtRun).where(PtRun.status == PtRunStatus.RUNNING.value)
            ).all()
        )
        if not runs:
            return 0

        ended_at = datetime.now(timezone.utc)
        for run in runs:
            run.status = PtRunStatus.FAILED.value
            run.stop_reason = PtRunStopReason.ENGINE_ERROR.value
            run.error_message = ORPHAN_ERROR_MESSAGE
            run.ended_at = ended_at

        session.commit()
        logger.info("Recovered %s orphaned PT run(s) after restart", len(runs))
        return len(runs)
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()

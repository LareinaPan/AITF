import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import database
from app.config import get_settings
from app.models.fc_experience_case import FcExperienceCase
from app.models.fc_generation_batch import FcGenerationBatch, FcGenerationBatchStatus
from app.models.fc_requirement_doc import FcRequirementDoc
from app.models.fc_test_case import FcTestCase, FcTestCaseStatus
from app.services.fc_ai_generator import (
    ExperienceCaseContext,
    FcGenerationInput,
    generate_functional_test_cases,
)
from app.services.fc_ai_reviewer import FcReviewInput, review_functional_test_cases

logger = logging.getLogger(__name__)


class FcGenerationPipelineError(Exception):
    """Raised when a generation batch pipeline fails."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_experience_cases(
    db: Session,
    fc_project_id: uuid.UUID,
    experience_case_ids: list[str],
) -> list[ExperienceCaseContext]:
    if not experience_case_ids:
        return []

    case_uuids = [uuid.UUID(case_id) for case_id in experience_case_ids]
    rows = list(
        db.scalars(
            select(FcExperienceCase).where(
                FcExperienceCase.fc_project_id == fc_project_id,
                FcExperienceCase.id.in_(case_uuids),
            )
        ).all()
    )
    return [
        ExperienceCaseContext(
            id=row.id,
            module=row.module,
            title=row.title,
            preconditions=row.preconditions,
            steps=row.steps,
            expected_result=row.expected_result,
            priority=row.priority,
            case_type=row.case_type,
        )
        for row in rows
    ]


def _replace_batch_draft_cases(
    db: Session,
    batch: FcGenerationBatch,
    cases: list[dict[str, Any]],
) -> None:
    settings = get_settings()
    limited_cases = cases[: settings.fc_max_cases_per_batch]

    db.execute(delete(FcTestCase).where(FcTestCase.generation_batch_id == batch.id))
    for case in limited_cases:
        db.add(
            FcTestCase(
                fc_project_id=batch.fc_project_id,
                requirement_doc_id=batch.requirement_doc_id,
                generation_batch_id=batch.id,
                case_no=case["case_no"],
                module=case["module"],
                title=case["title"],
                preconditions=case.get("preconditions"),
                steps=case["steps"],
                expected_result=case["expected_result"],
                priority=case["priority"],
                case_type=case["case_type"],
                status=FcTestCaseStatus.DRAFT.value,
            )
        )


def _build_review_suggestions(report: dict[str, Any]) -> str:
    gaps = report.get("gaps") or []
    suggestions = report.get("suggestions") or []
    lines = [*(str(item) for item in gaps), *(str(item) for item in suggestions)]
    return "\n".join(line for line in lines if line.strip())


def run_generation_batch(batch_id: uuid.UUID, db: Session | None = None) -> None:
    """Execute generate-review loop for one batch and persist draft cases."""
    owns_session = db is None
    session = db or database.SessionLocal()
    try:
        _execute_generation_batch(batch_id, session)
        if owns_session:
            session.commit()
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def _execute_generation_batch(batch_id: uuid.UUID, db: Session) -> None:
    batch = db.get(FcGenerationBatch, batch_id)
    if batch is None:
        raise FcGenerationPipelineError(f"Generation batch not found: {batch_id}")

    doc = db.get(FcRequirementDoc, batch.requirement_doc_id)
    if doc is None or not doc.parsed_text or not doc.parsed_text.strip():
        _mark_batch_failed(batch, db, "Requirement document is missing parsed text")
        return

    settings = get_settings()
    experience_cases = _load_experience_cases(db, batch.fc_project_id, batch.experience_case_ids)
    review_suggestions: str | None = None
    retry = 0
    final_report: dict[str, Any] | None = None

    try:
        while retry <= settings.fc_max_internal_retry:
            batch.status = FcGenerationBatchStatus.GENERATING.value
            db.commit()

            generation_result = generate_functional_test_cases(
                FcGenerationInput(
                    parsed_text=doc.parsed_text,
                    experience_cases=experience_cases,
                    user_feedback=batch.user_feedback,
                    review_suggestions=review_suggestions,
                )
            )
            _replace_batch_draft_cases(db, batch, generation_result.cases)

            batch.status = FcGenerationBatchStatus.REVIEWING.value
            db.commit()

            final_report = review_functional_test_cases(
                FcReviewInput(
                    parsed_text=doc.parsed_text,
                    generated_cases=generation_result.cases,
                )
            )
            batch.review_report_json = final_report
            batch.coverage_score = final_report["coverage_score"]

            if final_report.get("passed"):
                break
            if retry >= settings.fc_max_internal_retry:
                break

            review_suggestions = _build_review_suggestions(final_report)
            retry += 1
            batch.internal_retry_count = retry
            db.commit()

        batch.status = FcGenerationBatchStatus.AWAITING_REVIEW.value
        batch.completed_at = _utcnow()
        batch.error_message = None
        db.commit()
    except Exception as exc:
        logger.exception("FC generation batch %s failed", batch_id)
        db.rollback()
        batch = db.get(FcGenerationBatch, batch_id)
        if batch is not None:
            _mark_batch_failed(batch, db, str(exc))


def _mark_batch_failed(batch: FcGenerationBatch, db: Session, message: str) -> None:
    batch.status = FcGenerationBatchStatus.FAILED.value
    batch.error_message = message
    batch.completed_at = _utcnow()
    db.commit()


def enqueue_generation_batch(batch_id: uuid.UUID) -> None:
    """Background task entrypoint for FastAPI BackgroundTasks."""
    run_generation_batch(batch_id)


__all__ = [
    "FcGenerationPipelineError",
    "enqueue_generation_batch",
    "run_generation_batch",
]

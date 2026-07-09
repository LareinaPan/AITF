import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.fc_projects import get_fc_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_generation_batch import FcGenerationBatch, FcGenerationBatchStatus
from app.models.fc_test_case import FcTestCase, FcTestCaseStatus
from app.models.user import User
from app.schemas.fc_generation import (
    FcBatchConfirmRequest,
    FcBatchConfirmResponse,
    FcBatchRejectRequest,
    FcBatchRejectResponse,
    FcGenerationBatchResponse,
)
from app.schemas.fc_test_case import FcTestCaseResponse
from app.services.fc_ai_pipeline import enqueue_generation_batch

router = APIRouter()


def _to_batch_response(batch: FcGenerationBatch, case_count: int) -> FcGenerationBatchResponse:
    username = batch.trigger_user.username if batch.trigger_user is not None else "未知用户"
    return FcGenerationBatchResponse(
        id=batch.id,
        fc_project_id=batch.fc_project_id,
        requirement_doc_id=batch.requirement_doc_id,
        experience_case_ids=batch.experience_case_ids,
        status=batch.status,
        coverage_score=batch.coverage_score,
        review_report_json=batch.review_report_json,
        user_feedback=batch.user_feedback,
        internal_retry_count=batch.internal_retry_count,
        parent_batch_id=batch.parent_batch_id,
        triggered_by=batch.triggered_by,
        triggered_by_username=username,
        error_message=batch.error_message,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        case_count=case_count,
    )


def _load_batch_with_user(batch_id: uuid.UUID, db: Session) -> FcGenerationBatch:
    batch = db.scalar(
        select(FcGenerationBatch)
        .where(FcGenerationBatch.id == batch_id)
        .options(selectinload(FcGenerationBatch.trigger_user))
    )
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation batch not found",
        )
    return batch


def _ensure_batch_belongs_to_project(batch: FcGenerationBatch, fc_project_id: uuid.UUID) -> None:
    if batch.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation batch not found",
        )


def _count_batch_cases(batch_id: uuid.UUID, db: Session) -> int:
    return db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(FcTestCase.generation_batch_id == batch_id)
    ) or 0


def _count_batch_draft_cases(batch_id: uuid.UUID, db: Session) -> int:
    return db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(
            FcTestCase.generation_batch_id == batch_id,
            FcTestCase.status == FcTestCaseStatus.DRAFT.value,
        )
    ) or 0


def _ensure_batch_reviewable(batch: FcGenerationBatch) -> None:
    if batch.status != FcGenerationBatchStatus.AWAITING_REVIEW.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch is not awaiting user review",
        )


@router.get("", response_model=list[FcGenerationBatchResponse])
def list_generation_batches(
    fc_project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FcGenerationBatchResponse]:
    get_fc_project_or_404(fc_project_id, db)
    batches = list(
        db.scalars(
            select(FcGenerationBatch)
            .where(FcGenerationBatch.fc_project_id == fc_project_id)
            .options(selectinload(FcGenerationBatch.trigger_user))
            .order_by(FcGenerationBatch.created_at.desc())
        ).all()
    )
    return [
        _to_batch_response(batch, _count_batch_cases(batch.id, db))
        for batch in batches
    ]


@router.get("/{batch_id}", response_model=FcGenerationBatchResponse)
def get_generation_batch(
    fc_project_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcGenerationBatchResponse:
    get_fc_project_or_404(fc_project_id, db)
    batch = _load_batch_with_user(batch_id, db)
    _ensure_batch_belongs_to_project(batch, fc_project_id)
    return _to_batch_response(batch, _count_batch_cases(batch.id, db))


@router.get("/{batch_id}/cases", response_model=list[FcTestCaseResponse])
def list_batch_draft_cases(
    fc_project_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FcTestCaseResponse]:
    get_fc_project_or_404(fc_project_id, db)
    batch = _load_batch_with_user(batch_id, db)
    _ensure_batch_belongs_to_project(batch, fc_project_id)

    cases = list(
        db.scalars(
            select(FcTestCase)
            .where(
                FcTestCase.generation_batch_id == batch_id,
                FcTestCase.fc_project_id == fc_project_id,
                FcTestCase.status == FcTestCaseStatus.DRAFT.value,
            )
            .order_by(FcTestCase.case_no.asc())
        ).all()
    )
    return [FcTestCaseResponse.model_validate(case) for case in cases]


@router.post("/{batch_id}/confirm", response_model=FcBatchConfirmResponse)
def confirm_batch_cases(
    fc_project_id: uuid.UUID,
    batch_id: uuid.UUID,
    payload: FcBatchConfirmRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcBatchConfirmResponse:
    get_fc_project_or_404(fc_project_id, db)
    batch = db.get(FcGenerationBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation batch not found")
    _ensure_batch_belongs_to_project(batch, fc_project_id)
    _ensure_batch_reviewable(batch)

    draft_cases = list(
        db.scalars(
            select(FcTestCase).where(
                FcTestCase.generation_batch_id == batch_id,
                FcTestCase.fc_project_id == fc_project_id,
                FcTestCase.status == FcTestCaseStatus.DRAFT.value,
            )
        ).all()
    )
    if not draft_cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No draft cases available to confirm in this batch",
        )

    if payload.case_ids:
        selected_ids = set(payload.case_ids)
        cases_to_confirm = [case for case in draft_cases if case.id in selected_ids]
        if not cases_to_confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No matching draft cases found for the provided case_ids",
            )
        if len(cases_to_confirm) != len(selected_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more case_ids are invalid for this batch",
            )
    else:
        cases_to_confirm = draft_cases

    for case in cases_to_confirm:
        case.status = FcTestCaseStatus.ACTIVE.value

    remaining_draft = len(draft_cases) - len(cases_to_confirm)
    if remaining_draft <= 0:
        batch.status = FcGenerationBatchStatus.COMPLETED.value
        batch.completed_at = batch.completed_at or datetime.now(timezone.utc)

    db.commit()
    db.refresh(batch)
    return FcBatchConfirmResponse(
        confirmed_count=len(cases_to_confirm),
        batch_status=batch.status,
    )


@router.post("/{batch_id}/reject", response_model=FcBatchRejectResponse, status_code=status.HTTP_201_CREATED)
def reject_batch_and_regenerate(
    fc_project_id: uuid.UUID,
    batch_id: uuid.UUID,
    payload: FcBatchRejectRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FcBatchRejectResponse:
    get_fc_project_or_404(fc_project_id, db)
    batch = db.get(FcGenerationBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation batch not found")
    _ensure_batch_belongs_to_project(batch, fc_project_id)
    _ensure_batch_reviewable(batch)

    experience_case_ids = list(batch.experience_case_ids)
    new_batch = FcGenerationBatch(
        fc_project_id=batch.fc_project_id,
        requirement_doc_id=batch.requirement_doc_id,
        experience_case_ids=experience_case_ids,
        status=FcGenerationBatchStatus.PENDING.value,
        user_feedback=payload.feedback.strip(),
        parent_batch_id=batch.id,
        triggered_by=current_user.id,
    )
    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)
    background_tasks.add_task(enqueue_generation_batch, new_batch.id)
    return FcBatchRejectResponse(
        batch_id=new_batch.id,
        status=new_batch.status,
        parent_batch_id=batch.id,
    )

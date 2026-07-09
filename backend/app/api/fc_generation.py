import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.fc_projects import get_fc_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_experience_case import FcExperienceCase
from app.models.fc_generation_batch import FcGenerationBatch, FcGenerationBatchStatus
from app.models.fc_requirement_doc import FcRequirementDoc, FcRequirementParseStatus
from app.models.user import User
from app.schemas.fc_generation import FcGenerateRequest, FcGenerateResponse
from app.services.fc_ai_pipeline import enqueue_generation_batch

router = APIRouter()


def _validate_requirement_doc(
    fc_project_id: uuid.UUID,
    requirement_doc_id: uuid.UUID,
    db: Session,
) -> FcRequirementDoc:
    doc = db.get(FcRequirementDoc, requirement_doc_id)
    if doc is None or doc.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid requirement_doc_id for this project",
        )
    if doc.parse_status != FcRequirementParseStatus.SUCCESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requirement document must be parsed successfully before generation",
        )
    if not doc.parsed_text or not doc.parsed_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requirement document has no parsed text",
        )
    return doc


def _validate_experience_case_ids(
    fc_project_id: uuid.UUID,
    experience_case_ids: list[uuid.UUID],
    db: Session,
) -> list[str]:
    if not experience_case_ids:
        return []

    cases = list(
        db.scalars(
            select(FcExperienceCase).where(
                FcExperienceCase.id.in_(experience_case_ids),
                FcExperienceCase.fc_project_id == fc_project_id,
            )
        ).all()
    )
    if len(cases) != len(set(experience_case_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more experience_case_ids are invalid for this project",
        )
    return [str(case_id) for case_id in experience_case_ids]


def _validate_parent_batch(
    fc_project_id: uuid.UUID,
    parent_batch_id: uuid.UUID | None,
    db: Session,
) -> None:
    if parent_batch_id is None:
        return

    batch = db.get(FcGenerationBatch, parent_batch_id)
    if batch is None or batch.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid parent_batch_id for this project",
        )


@router.post("/generate", response_model=FcGenerateResponse, status_code=status.HTTP_201_CREATED)
def start_fc_generation(
    fc_project_id: uuid.UUID,
    payload: FcGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FcGenerateResponse:
    get_fc_project_or_404(fc_project_id, db)
    _validate_requirement_doc(fc_project_id, payload.requirement_doc_id, db)
    experience_case_id_strings = _validate_experience_case_ids(
        fc_project_id,
        payload.experience_case_ids,
        db,
    )
    _validate_parent_batch(fc_project_id, payload.parent_batch_id, db)

    batch = FcGenerationBatch(
        fc_project_id=fc_project_id,
        requirement_doc_id=payload.requirement_doc_id,
        experience_case_ids=experience_case_id_strings,
        status=FcGenerationBatchStatus.PENDING.value,
        user_feedback=payload.user_feedback,
        parent_batch_id=payload.parent_batch_id,
        triggered_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(enqueue_generation_batch, batch.id)
    return FcGenerateResponse(batch_id=batch.id, status=batch.status)

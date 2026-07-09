import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_experience_case import FcExperienceCase
from app.models.fc_generation_batch import FcGenerationBatch
from app.models.fc_project import FcProject
from app.models.fc_requirement_doc import FcRequirementDoc
from app.models.fc_test_case import FcTestCase, FcTestCaseStatus
from app.models.user import User
from app.schemas.fc_project import (
    FcProjectCreateRequest,
    FcProjectResponse,
    FcProjectStatsResponse,
    FcProjectUpdateRequest,
)

router = APIRouter()


def _to_fc_project_response(project: FcProject) -> FcProjectResponse:
    creator_name = project.creator.username if project.creator is not None else "未知用户"
    return FcProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        created_by_username=creator_name,
        created_at=project.created_at,
    )


def get_fc_project_or_404(project_id: uuid.UUID, db: Session) -> FcProject:
    project = db.get(FcProject, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Functional project not found",
        )
    return project


def _load_fc_project_with_creator(project_id: uuid.UUID, db: Session) -> FcProject:
    project = db.scalar(
        select(FcProject)
        .where(FcProject.id == project_id)
        .options(selectinload(FcProject.creator))
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Functional project not found",
        )
    return project


@router.get("", response_model=list[FcProjectResponse])
def list_fc_projects(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FcProjectResponse]:
    projects = list(
        db.scalars(
            select(FcProject)
            .options(selectinload(FcProject.creator))
            .order_by(FcProject.created_at.desc())
        ).all()
    )
    return [_to_fc_project_response(project) for project in projects]


@router.post("", response_model=FcProjectResponse, status_code=status.HTTP_201_CREATED)
def create_fc_project(
    payload: FcProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FcProjectResponse:
    project = FcProject(
        name=payload.name.strip(),
        description=payload.description,
        created_by=current_user.id,
    )
    db.add(project)
    db.commit()
    return _to_fc_project_response(_load_fc_project_with_creator(project.id, db))


@router.get("/{project_id}", response_model=FcProjectResponse)
def get_fc_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcProjectResponse:
    return _to_fc_project_response(_load_fc_project_with_creator(project_id, db))


@router.get("/{project_id}/stats", response_model=FcProjectStatsResponse)
def get_fc_project_stats(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcProjectStatsResponse:
    get_fc_project_or_404(project_id, db)

    doc_count = db.scalar(
        select(func.count())
        .select_from(FcRequirementDoc)
        .where(FcRequirementDoc.fc_project_id == project_id)
    ) or 0
    experience_case_count = db.scalar(
        select(func.count())
        .select_from(FcExperienceCase)
        .where(FcExperienceCase.fc_project_id == project_id)
    ) or 0
    active_case_count = db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(
            FcTestCase.fc_project_id == project_id,
            FcTestCase.status == FcTestCaseStatus.ACTIVE.value,
        )
    ) or 0
    draft_case_count = db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(
            FcTestCase.fc_project_id == project_id,
            FcTestCase.status == FcTestCaseStatus.DRAFT.value,
        )
    ) or 0
    batch_count = db.scalar(
        select(func.count())
        .select_from(FcGenerationBatch)
        .where(FcGenerationBatch.fc_project_id == project_id)
    ) or 0
    last_batch_at = db.scalar(
        select(func.max(FcGenerationBatch.created_at)).where(
            FcGenerationBatch.fc_project_id == project_id
        )
    )

    return FcProjectStatsResponse(
        doc_count=doc_count,
        experience_case_count=experience_case_count,
        active_case_count=active_case_count,
        draft_case_count=draft_case_count,
        batch_count=batch_count,
        last_batch_at=last_batch_at,
    )


@router.put("/{project_id}", response_model=FcProjectResponse)
def update_fc_project(
    project_id: uuid.UUID,
    payload: FcProjectUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcProjectResponse:
    project = get_fc_project_or_404(project_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "name" in update_data and update_data["name"] is not None:
        update_data["name"] = update_data["name"].strip()

    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    return _to_fc_project_response(_load_fc_project_with_creator(project_id, db))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fc_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    project = get_fc_project_or_404(project_id, db)
    db.delete(project)
    db.commit()

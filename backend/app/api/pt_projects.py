import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models.pt_project import PtProject
from app.models.pt_scenario import PtScenario
from app.models.user import User
from app.schemas.pt_project import (
    PtProjectCreateRequest,
    PtProjectResponse,
    PtProjectStatsResponse,
    PtProjectUpdateRequest,
)
from app.services.pt_project_delete_service import (
    PtProjectDeleteError,
    PtProjectRunningError,
    delete_pt_project as delete_pt_project_service,
)

router = APIRouter()


def _to_pt_project_response(project: PtProject) -> PtProjectResponse:
    creator_name = project.creator.username if project.creator is not None else "未知用户"
    return PtProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        created_by_username=creator_name,
        created_at=project.created_at,
    )


def get_pt_project_or_404(project_id: uuid.UUID, db: Session) -> PtProject:
    project = db.get(PtProject, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance project not found",
        )
    return project


def _load_pt_project_with_creator(project_id: uuid.UUID, db: Session) -> PtProject:
    project = db.scalar(
        select(PtProject)
        .where(PtProject.id == project_id)
        .options(selectinload(PtProject.creator))
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance project not found",
        )
    return project


@router.get("", response_model=list[PtProjectResponse])
def list_pt_projects(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PtProjectResponse]:
    projects = list(
        db.scalars(
            select(PtProject)
            .options(selectinload(PtProject.creator))
            .order_by(PtProject.created_at.desc())
        ).all()
    )
    return [_to_pt_project_response(project) for project in projects]


@router.post("", response_model=PtProjectResponse, status_code=status.HTTP_201_CREATED)
def create_pt_project(
    payload: PtProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PtProjectResponse:
    project = PtProject(
        name=payload.name.strip(),
        description=payload.description,
        created_by=current_user.id,
    )
    db.add(project)
    db.commit()
    return _to_pt_project_response(_load_pt_project_with_creator(project.id, db))


@router.get("/{project_id}", response_model=PtProjectResponse)
def get_pt_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtProjectResponse:
    return _to_pt_project_response(_load_pt_project_with_creator(project_id, db))


@router.get("/{project_id}/stats", response_model=PtProjectStatsResponse)
def get_pt_project_stats(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtProjectStatsResponse:
    get_pt_project_or_404(project_id, db)
    scenario_count = db.scalar(
        select(func.count())
        .select_from(PtScenario)
        .where(PtScenario.pt_project_id == project_id)
    ) or 0
    return PtProjectStatsResponse(
        scenario_count=scenario_count,
        run_count=0,
        last_run_at=None,
        last_run_status=None,
    )


@router.put("/{project_id}", response_model=PtProjectResponse)
def update_pt_project(
    project_id: uuid.UUID,
    payload: PtProjectUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtProjectResponse:
    project = get_pt_project_or_404(project_id, db)
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
    return _to_pt_project_response(_load_pt_project_with_creator(project_id, db))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pt_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    try:
        delete_pt_project_service(db, project_id)
    except PtProjectRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PtProjectDeleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

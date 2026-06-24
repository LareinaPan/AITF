import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter()


def _to_project_response(project: Project) -> ProjectResponse:
    creator_name = project.creator.username if project.creator is not None else "未知用户"
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        feishu_webhook_url=project.feishu_webhook_url,
        created_by=project.created_by,
        created_by_username=creator_name,
        created_at=project.created_at,
    )


def get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def _load_project_with_creator(project_id: uuid.UUID, db: Session) -> Project:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.creator))
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    projects = list(
        db.scalars(
            select(Project)
            .options(selectinload(Project.creator))
            .order_by(Project.created_at.desc())
        ).all()
    )
    return [_to_project_response(project) for project in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = Project(
        name=payload.name.strip(),
        description=payload.description,
        feishu_webhook_url=payload.feishu_webhook_url,
        created_by=current_user.id,
    )
    db.add(project)
    db.commit()
    return _to_project_response(_load_project_with_creator(project.id, db))


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectResponse:
    return _to_project_response(_load_project_with_creator(project_id, db))


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectResponse:
    project = get_project_or_404(project_id, db)
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
    return _to_project_response(_load_project_with_creator(project_id, db))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    project = get_project_or_404(project_id, db)
    db.delete(project)
    db.commit()

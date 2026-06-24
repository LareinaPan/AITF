import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.environment import Environment, EnvironmentVariable
from app.models.test_plan import TestPlan
from app.models.user import User
from app.schemas.environment import (
    EnvironmentCreateRequest,
    EnvironmentResponse,
    EnvironmentUpdateRequest,
    EnvironmentVariableResponse,
    EnvironmentVariablesBatchRequest,
)

router = APIRouter()


def get_environment_or_404(environment_id: uuid.UUID, db: Session) -> Environment:
    environment = db.get(Environment, environment_id)
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )
    return environment


def clear_other_default_flags(db: Session, exclude_id: uuid.UUID | None = None) -> None:
    stmt = update(Environment).values(is_default=False)
    if exclude_id is not None:
        stmt = stmt.where(Environment.id != exclude_id)
    db.execute(stmt)


@router.get("", response_model=list[EnvironmentResponse])
def list_environments(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Environment]:
    return list(db.scalars(select(Environment).order_by(Environment.name.asc())).all())


@router.post("", response_model=EnvironmentResponse, status_code=status.HTTP_201_CREATED)
def create_environment(
    payload: EnvironmentCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Environment:
    existing = db.scalar(select(Environment).where(Environment.name == payload.name))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Environment name already exists",
        )

    if payload.is_default:
        clear_other_default_flags(db)

    environment = Environment(name=payload.name, is_default=payload.is_default)
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment


@router.get("/{environment_id}", response_model=EnvironmentResponse)
def get_environment(
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Environment:
    return get_environment_or_404(environment_id, db)


@router.put("/{environment_id}", response_model=EnvironmentResponse)
def update_environment(
    environment_id: uuid.UUID,
    payload: EnvironmentUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Environment:
    environment = get_environment_or_404(environment_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "name" in update_data and update_data["name"] != environment.name:
        duplicate = db.scalar(
            select(Environment).where(Environment.name == update_data["name"])
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Environment name already exists",
            )

    if update_data.get("is_default") is True:
        clear_other_default_flags(db, exclude_id=environment.id)

    for field, value in update_data.items():
        setattr(environment, field, value)

    db.commit()
    db.refresh(environment)
    return environment


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    environment = get_environment_or_404(environment_id, db)

    plan_count = db.scalar(
        select(func.count())
        .select_from(TestPlan)
        .where(TestPlan.environment_id == environment_id)
    )
    if plan_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete environment: it is used by test plans",
        )

    db.delete(environment)
    db.commit()


@router.get("/{environment_id}/variables", response_model=list[EnvironmentVariableResponse])
def list_environment_variables(
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[EnvironmentVariable]:
    get_environment_or_404(environment_id, db)
    return list(
        db.scalars(
            select(EnvironmentVariable)
            .where(EnvironmentVariable.environment_id == environment_id)
            .order_by(EnvironmentVariable.key.asc())
        ).all()
    )


@router.put("/{environment_id}/variables", response_model=list[EnvironmentVariableResponse])
def save_environment_variables(
    environment_id: uuid.UUID,
    payload: EnvironmentVariablesBatchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[EnvironmentVariable]:
    get_environment_or_404(environment_id, db)

    db.execute(
        delete(EnvironmentVariable).where(
            EnvironmentVariable.environment_id == environment_id
        )
    )

    variables = [
        EnvironmentVariable(
            environment_id=environment_id,
            key=item.key,
            value=item.value,
            is_secret=item.is_secret,
        )
        for item in payload.variables
    ]
    db.add_all(variables)
    db.commit()

    return list(
        db.scalars(
            select(EnvironmentVariable)
            .where(EnvironmentVariable.environment_id == environment_id)
            .order_by(EnvironmentVariable.key.asc())
        ).all()
    )

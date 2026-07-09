import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.pt_projects import get_pt_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.pt_scenario import PtScenario
from app.models.pt_script import PtScript, PtScriptParseStatus, PtScriptStopMode
from app.models.user import User
from app.schemas.pt_scenario import (
    PtScenarioCreateRequest,
    PtScenarioResponse,
    PtScenarioUpdateRequest,
)

router = APIRouter()


def _to_pt_scenario_response(scenario: PtScenario) -> PtScenarioResponse:
    if scenario.script is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scenario script is missing",
        )
    return PtScenarioResponse(
        id=scenario.id,
        pt_project_id=scenario.pt_project_id,
        name=scenario.name,
        description=scenario.description,
        script_id=scenario.script.id,
        parse_status=scenario.script.parse_status,
        last_run_status=None,
        last_run_at=None,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def _load_scenario_with_script(scenario_id: uuid.UUID, db: Session) -> PtScenario:
    scenario = db.scalar(
        select(PtScenario)
        .where(PtScenario.id == scenario_id)
        .options(selectinload(PtScenario.script))
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance scenario not found",
        )
    return scenario


def get_pt_scenario_or_404(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session,
) -> PtScenario:
    scenario = db.scalar(
        select(PtScenario)
        .where(
            PtScenario.id == scenario_id,
            PtScenario.pt_project_id == project_id,
        )
        .options(selectinload(PtScenario.script))
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance scenario not found",
        )
    return scenario


@router.get("", response_model=list[PtScenarioResponse])
def list_pt_scenarios(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PtScenarioResponse]:
    get_pt_project_or_404(project_id, db)
    scenarios = list(
        db.scalars(
            select(PtScenario)
            .where(PtScenario.pt_project_id == project_id)
            .options(selectinload(PtScenario.script))
            .order_by(PtScenario.created_at.desc())
        ).all()
    )
    return [_to_pt_scenario_response(scenario) for scenario in scenarios]


@router.post("", response_model=PtScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_pt_scenario(
    project_id: uuid.UUID,
    payload: PtScenarioCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScenarioResponse:
    get_pt_project_or_404(project_id, db)

    scenario = PtScenario(
        pt_project_id=project_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    scenario.script = PtScript(
        parse_status=PtScriptParseStatus.PENDING.value,
        stop_mode=PtScriptStopMode.DURATION.value,
    )
    db.add(scenario)
    db.commit()
    return _to_pt_scenario_response(_load_scenario_with_script(scenario.id, db))


@router.get("/{scenario_id}", response_model=PtScenarioResponse)
def get_pt_scenario(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScenarioResponse:
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    return _to_pt_scenario_response(scenario)


@router.put("/{scenario_id}", response_model=PtScenarioResponse)
def update_pt_scenario(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    payload: PtScenarioUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScenarioResponse:
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "name" in update_data and update_data["name"] is not None:
        update_data["name"] = update_data["name"].strip()

    for field, value in update_data.items():
        setattr(scenario, field, value)

    db.commit()
    return _to_pt_scenario_response(_load_scenario_with_script(scenario_id, db))


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pt_scenario(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    db.delete(scenario)
    db.commit()

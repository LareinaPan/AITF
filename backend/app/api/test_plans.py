import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.environments import get_environment_or_404
from app.api.projects import get_project_or_404
from app.api.test_cases import get_test_case_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, PlanRun, TestPlan
from app.models.user import User
from app.scheduler.plan_jobs import sync_plan_scheduler_jobs
from app.schemas.test_plan import (
    PlanCaseBindRequest,
    PlanCaseItemResponse,
    PlanRunResponse,
    TestPlanCreateRequest,
    TestPlanDetailResponse,
    TestPlanResponse,
    TestPlanUpdateRequest,
)
from app.services.plan_execution_service import execute_test_plan
from app.services.test_plan_service import (
    PlanCaseBindingError,
    resolve_new_case_ids,
    validate_cases_are_active,
    validate_plan_case_capacity,
)
from app.services.cron_validator import CronExpressionError, validate_enabled_cron
from app.services.test_runner import TestPlanNotFoundError

router = APIRouter()


def _refresh_plan_scheduler(request: Request, db: Session) -> None:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        sync_plan_scheduler_jobs(scheduler, db)


def get_test_plan_or_404(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session,
) -> TestPlan:
    plan = db.get(TestPlan, plan_id)
    if plan is None or plan.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test plan not found",
        )
    return plan


def _build_plan_case_items(plan: TestPlan) -> list[PlanCaseItemResponse]:
    return [
        PlanCaseItemResponse(
            case_id=plan_case.case_id,
            case_name=plan_case.test_case.name,
            sort_order=plan_case.sort_order,
            status=plan_case.test_case.status,
        )
        for plan_case in plan.plan_cases
    ]


def _format_environment_name(plan: TestPlan) -> str:
    environment = plan.environment
    if environment is None:
        return "未知环境"
    if environment.is_default:
        return f"{environment.name}（默认）"
    return environment.name


def _to_plan_response(plan: TestPlan) -> TestPlanResponse:
    return TestPlanResponse(
        id=plan.id,
        project_id=plan.project_id,
        name=plan.name,
        cron_expression=plan.cron_expression,
        environment_id=plan.environment_id,
        environment_name=_format_environment_name(plan),
        is_enabled=plan.is_enabled,
        notify_on_complete=plan.notify_on_complete,
        created_at=plan.created_at,
        case_count=len(plan.plan_cases),
    )


def _to_plan_detail_response(plan: TestPlan) -> TestPlanDetailResponse:
    base = _to_plan_response(plan)
    return TestPlanDetailResponse(
        **base.model_dump(),
        cases=_build_plan_case_items(plan),
    )


def _load_plan_with_cases(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session,
) -> TestPlan:
    plan = db.scalar(
        select(TestPlan)
        .where(TestPlan.id == plan_id, TestPlan.project_id == project_id)
        .options(
            selectinload(TestPlan.plan_cases).selectinload(PlanCase.test_case),
            selectinload(TestPlan.environment),
        )
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test plan not found",
        )
    return plan


@router.get("", response_model=list[TestPlanResponse])
def list_test_plans(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TestPlanResponse]:
    get_project_or_404(project_id, db)
    plans = list(
        db.scalars(
            select(TestPlan)
            .where(TestPlan.project_id == project_id)
            .options(
                selectinload(TestPlan.plan_cases),
                selectinload(TestPlan.environment),
            )
            .order_by(TestPlan.created_at.desc())
        ).all()
    )
    return [_to_plan_response(plan) for plan in plans]


@router.post("", response_model=TestPlanResponse, status_code=status.HTTP_201_CREATED)
def create_test_plan(
    project_id: uuid.UUID,
    payload: TestPlanCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPlanResponse:
    get_project_or_404(project_id, db)
    get_environment_or_404(payload.environment_id, db)

    plan = TestPlan(
        project_id=project_id,
        name=payload.name,
        environment_id=payload.environment_id,
        cron_expression=payload.cron_expression,
        is_enabled=payload.is_enabled,
        notify_on_complete=payload.notify_on_complete,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    plan = db.scalar(
        select(TestPlan)
        .where(TestPlan.id == plan.id)
        .options(selectinload(TestPlan.plan_cases), selectinload(TestPlan.environment))
    )
    assert plan is not None
    _refresh_plan_scheduler(request, db)
    return _to_plan_response(plan)


@router.get("/{plan_id}", response_model=TestPlanDetailResponse)
def get_test_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPlanDetailResponse:
    get_project_or_404(project_id, db)
    plan = _load_plan_with_cases(project_id, plan_id, db)
    return _to_plan_detail_response(plan)


@router.put("/{plan_id}", response_model=TestPlanResponse)
def update_test_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: TestPlanUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPlanResponse:
    get_project_or_404(project_id, db)
    plan = get_test_plan_or_404(project_id, plan_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "environment_id" in update_data and update_data["environment_id"] is not None:
        get_environment_or_404(update_data["environment_id"], db)

    effective_is_enabled = update_data.get("is_enabled", plan.is_enabled)
    effective_cron = update_data.get("cron_expression", plan.cron_expression)
    try:
        validate_enabled_cron(
            is_enabled=effective_is_enabled,
            cron_expression=effective_cron,
        )
    except CronExpressionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    for field, value in update_data.items():
        setattr(plan, field, value)

    db.commit()
    plan = db.scalar(
        select(TestPlan)
        .where(TestPlan.id == plan_id)
        .options(
            selectinload(TestPlan.plan_cases),
            selectinload(TestPlan.environment),
        )
    )
    assert plan is not None
    _refresh_plan_scheduler(request, db)
    return _to_plan_response(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_project_or_404(project_id, db)
    plan = get_test_plan_or_404(project_id, plan_id, db)
    db.delete(plan)
    db.commit()
    _refresh_plan_scheduler(request, db)


@router.post("/{plan_id}/cases", response_model=TestPlanDetailResponse)
def bind_plan_cases(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: PlanCaseBindRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPlanDetailResponse:
    get_project_or_404(project_id, db)
    plan = _load_plan_with_cases(project_id, plan_id, db)

    existing_case_ids = {plan_case.case_id for plan_case in plan.plan_cases}
    new_case_ids = resolve_new_case_ids(payload.case_ids, existing_case_ids)

    if not new_case_ids:
        return _to_plan_detail_response(plan)

    try:
        validate_plan_case_capacity(len(plan.plan_cases), len(new_case_ids))
    except PlanCaseBindingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    test_cases = list(
        db.scalars(
            select(TestCase).where(
                TestCase.project_id == project_id,
                TestCase.id.in_(new_case_ids),
            )
        ).all()
    )
    cases_by_id = {test_case.id: test_case for test_case in test_cases}

    missing_case_ids = [case_id for case_id in new_case_ids if case_id not in cases_by_id]
    if missing_case_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found",
        )

    ordered_cases = [cases_by_id[case_id] for case_id in new_case_ids]
    try:
        validate_cases_are_active(ordered_cases)
    except PlanCaseBindingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    max_sort_order = max((plan_case.sort_order for plan_case in plan.plan_cases), default=-1)
    for index, case_id in enumerate(new_case_ids):
        db.add(
            PlanCase(
                plan_id=plan.id,
                case_id=case_id,
                sort_order=max_sort_order + 1 + index,
            )
        )

    db.commit()
    plan = _load_plan_with_cases(project_id, plan_id, db)
    return _to_plan_detail_response(plan)


@router.delete("/{plan_id}/cases/{case_id}", response_model=TestPlanDetailResponse)
def unbind_plan_case(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPlanDetailResponse:
    get_project_or_404(project_id, db)
    get_test_case_or_404(project_id, case_id, db)
    plan = get_test_plan_or_404(project_id, plan_id, db)

    plan_case = db.scalar(
        select(PlanCase).where(
            PlanCase.plan_id == plan.id,
            PlanCase.case_id == case_id,
        )
    )
    if plan_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case is not bound to this plan",
        )

    db.delete(plan_case)
    db.commit()

    plan = _load_plan_with_cases(project_id, plan_id, db)
    return _to_plan_detail_response(plan)


@router.post("/{plan_id}/run", response_model=PlanRunResponse)
def run_test_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PlanRun:
    get_project_or_404(project_id, db)
    get_test_plan_or_404(project_id, plan_id, db)

    try:
        plan_run, _ = execute_test_plan(db, plan_id, trigger="manual")
    except TestPlanNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return plan_run


@router.get("/{plan_id}/runs", response_model=list[PlanRunResponse])
def list_plan_runs(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PlanRun]:
    get_project_or_404(project_id, db)
    get_test_plan_or_404(project_id, plan_id, db)

    return list(
        db.scalars(
            select(PlanRun)
            .where(PlanRun.plan_id == plan_id)
            .order_by(PlanRun.created_at.desc())
        ).all()
    )

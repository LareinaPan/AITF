import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.pt_projects import get_pt_project_or_404
from app.api.pt_scenarios import get_pt_scenario_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.user import User
from app.schemas.pt_run import (
    PtRunActionResponse,
    PtRunErrorLogListResponse,
    PtRunErrorLogResponse,
    PtRunListItemResponse,
    PtRunListResponse,
    PtRunMetricPointResponse,
    PtRunMetricsResponse,
    PtRunResponse,
)
from app.services.pt_error_log_sanitizer import sanitize_error_message
from app.services.pt_run_orchestrator import (
    PtRunNotRunningError,
    PtRunOrchestratorError,
    build_config_snapshot_from_script,
    cancel_load_test,
    get_run_aggregator,
    is_run_slot_busy,
    schedule_load_test,
    validate_script_ready_for_run,
)

router = APIRouter()


def _get_pt_run_or_404(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session,
) -> PtRun:
    run = db.get(PtRun, run_id)
    if run is None or run.pt_project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance run not found",
        )
    return run


def _resolve_run_summary_json(run: PtRun) -> dict[str, Any] | None:
    if run.status == PtRunStatus.RUNNING.value:
        aggregator = get_run_aggregator(run.id)
        if aggregator is not None:
            return aggregator.build_interim_summary_json(
                run_id=run.id,
                status=run.status,
                started_at=run.started_at,
                stop_reason=None,
            )
    return run.summary_json


def _to_pt_run_list_item(run: PtRun) -> PtRunListItemResponse:
    return PtRunListItemResponse(
        id=run.id,
        pt_project_id=run.pt_project_id,
        pt_scenario_id=run.pt_scenario_id,
        scenario_name_snapshot=run.scenario_name_snapshot,
        status=run.status,
        stop_reason=run.stop_reason,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        ended_at=run.ended_at,
    )


def _to_pt_run_response(run: PtRun) -> PtRunResponse:
    return PtRunResponse(
        **_to_pt_run_list_item(run).model_dump(),
        config_snapshot_json=run.config_snapshot_json,
        summary_json=_resolve_run_summary_json(run),
        error_message=run.error_message,
    )


def _to_pt_run_error_log_response(log: PtRunErrorLog) -> PtRunErrorLogResponse:
    return PtRunErrorLogResponse(
        id=log.id,
        occurred_at=log.occurred_at,
        sampler_key=log.sampler_key,
        sampler_name=log.sampler_name,
        status_code=log.status_code,
        error_type=log.error_type,
        message=sanitize_error_message(log.message),
    )


@router.get("/runs", response_model=PtRunListResponse)
def list_pt_runs(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtRunListResponse:
    get_pt_project_or_404(project_id, db)

    base_query = select(PtRun).where(PtRun.pt_project_id == project_id)
    if scenario_id is not None:
        base_query = base_query.where(PtRun.pt_scenario_id == scenario_id)
    if status_filter is not None:
        base_query = base_query.where(PtRun.status == status_filter)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query)
    assert total is not None

    offset = (page - 1) * page_size
    runs = list(
        db.scalars(
            base_query.order_by(PtRun.started_at.desc()).offset(offset).limit(page_size)
        ).all()
    )
    return PtRunListResponse(
        items=[_to_pt_run_list_item(run) for run in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=PtRunResponse)
def get_pt_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtRunResponse:
    get_pt_project_or_404(project_id, db)
    run = _get_pt_run_or_404(project_id, run_id, db)
    return _to_pt_run_response(run)


def _normalize_query_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/runs/{run_id}/metrics", response_model=PtRunMetricsResponse)
def get_pt_run_metrics(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    sampler_key: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtRunMetricsResponse:
    get_pt_project_or_404(project_id, db)
    _get_pt_run_or_404(project_id, run_id, db)

    query = select(PtRunMetricPoint).where(PtRunMetricPoint.pt_run_id == run_id)
    if sampler_key is not None:
        query = query.where(PtRunMetricPoint.sampler_key == sampler_key)
    if since is not None:
        since_utc = _normalize_query_datetime(since)
        query = query.where(PtRunMetricPoint.recorded_at > since_utc)

    points = list(
        db.scalars(query.order_by(PtRunMetricPoint.recorded_at.asc())).all()
    )
    return PtRunMetricsResponse(
        items=[PtRunMetricPointResponse.model_validate(point) for point in points]
    )


@router.get("/runs/{run_id}/errors", response_model=PtRunErrorLogListResponse)
def get_pt_run_errors(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    latest: int | None = Query(default=None, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtRunErrorLogListResponse:
    get_pt_project_or_404(project_id, db)
    _get_pt_run_or_404(project_id, run_id, db)

    base_query = select(PtRunErrorLog).where(PtRunErrorLog.pt_run_id == run_id)

    if latest is not None:
        logs = list(
            db.scalars(
                base_query.order_by(PtRunErrorLog.occurred_at.desc()).limit(latest)
            ).all()
        )
        return PtRunErrorLogListResponse(
            items=[_to_pt_run_error_log_response(log) for log in logs]
        )

    total = db.scalar(select(func.count()).select_from(base_query.subquery()))
    assert total is not None

    offset = (page - 1) * page_size
    logs = list(
        db.scalars(
            base_query.order_by(PtRunErrorLog.occurred_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    return PtRunErrorLogListResponse(
        items=[_to_pt_run_error_log_response(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/scenarios/{scenario_id}/run",
    response_model=PtRunActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_pt_run(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PtRunActionResponse:
    get_pt_project_or_404(project_id, db)
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    if scenario.script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance script not found",
        )

    try:
        validate_script_ready_for_run(scenario.script)
    except PtRunOrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if is_run_slot_busy(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another load test is already running",
        )

    started_at = datetime.now(timezone.utc)
    run = PtRun(
        pt_project_id=project_id,
        pt_scenario_id=scenario.id,
        scenario_name_snapshot=scenario.name,
        status=PtRunStatus.RUNNING.value,
        config_snapshot_json=build_config_snapshot_from_script(scenario.script),
        triggered_by=current_user.id,
        started_at=started_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(schedule_load_test, run.id)
    return PtRunActionResponse(run_id=run.id, status=PtRunStatus.RUNNING.value)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=PtRunActionResponse,
)
async def cancel_pt_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtRunActionResponse:
    get_pt_project_or_404(project_id, db)
    run = _get_pt_run_or_404(project_id, run_id, db)

    if run.status != PtRunStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only running load tests can be cancelled",
        )

    try:
        await cancel_load_test(run_id)
    except PtRunNotRunningError:
        # Engine already gone (e.g. process restart); still mark the DB row cancelled.
        pass

    run.status = PtRunStatus.CANCELLED.value
    run.stop_reason = PtRunStopReason.MANUAL_CANCEL.value
    run.ended_at = datetime.now(timezone.utc)
    db.commit()

    return PtRunActionResponse(run_id=run.id, status=PtRunStatus.CANCELLED.value)

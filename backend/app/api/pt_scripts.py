import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.pt_scenarios import get_pt_scenario_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.pt_script import PtScript, PtScriptParseStatus, PtScriptStopMode
from app.models.user import User
from app.schemas.pt_script import (
    ParsedJmxPlanSchema,
    PtScriptConfigUpdate,
    PtScriptResponse,
    PtScriptUploadResponse,
)
from app.services.pt_jmx_parser import (
    PtJmxParseError,
    PtJmxSizeLimitError,
    UnsupportedPtJmxFormatError,
    delete_pt_jmx_file,
    parse_jmx_content,
    resolve_file_type,
    save_pt_jmx_upload,
)

router = APIRouter()


def _build_parsed_plan_schema(parsed_plan_json: dict | None) -> ParsedJmxPlanSchema | None:
    if not parsed_plan_json:
        return None
    return ParsedJmxPlanSchema.model_validate(parsed_plan_json)


def _to_pt_script_response(script: PtScript) -> PtScriptResponse:
    parsed_plan = _build_parsed_plan_schema(script.parsed_plan_json)
    sampler_count = len(parsed_plan.samplers) if parsed_plan is not None else 0
    thread_group_count = len(parsed_plan.thread_groups) if parsed_plan is not None else 0
    return PtScriptResponse(
        id=script.id,
        pt_scenario_id=script.pt_scenario_id,
        filename=script.filename,
        file_size=script.file_size,
        parse_status=script.parse_status,
        parse_error=script.parse_error,
        parsed_plan=parsed_plan,
        sampler_count=sampler_count,
        thread_group_count=thread_group_count,
        max_concurrency=script.max_concurrency,
        ramp_up_seconds=script.ramp_up_seconds,
        stop_mode=script.stop_mode,
        duration_seconds=script.duration_seconds,
        default_max_requests=script.default_max_requests,
        sampler_limits=script.sampler_limits_json,
        uploaded_at=script.uploaded_at,
        updated_at=script.updated_at,
    )


def _get_script_or_404(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session,
) -> PtScript:
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    if scenario.script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance script not found",
        )
    return scenario.script


def _validate_sampler_limits_for_script(
    script: PtScript,
    sampler_limits: dict[str, int] | None,
) -> None:
    if not sampler_limits:
        return
    if not script.parsed_plan_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set sampler_limits without a successfully parsed script",
        )
    valid_keys = {
        sampler["key"]
        for sampler in script.parsed_plan_json.get("samplers", [])
        if sampler.get("key")
    }
    unknown_keys = sorted(set(sampler_limits.keys()) - valid_keys)
    if unknown_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown sampler keys: {', '.join(unknown_keys)}",
        )


@router.get("", response_model=PtScriptResponse)
def get_pt_script(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScriptResponse:
    script = _get_script_or_404(project_id, scenario_id, db)
    return _to_pt_script_response(script)


@router.put("/config", response_model=PtScriptResponse)
def update_pt_script_config(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    body: PtScriptConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScriptResponse:
    script = _get_script_or_404(project_id, scenario_id, db)
    _validate_sampler_limits_for_script(script, body.sampler_limits)

    script.max_concurrency = body.max_concurrency
    script.ramp_up_seconds = body.ramp_up_seconds
    script.stop_mode = body.stop_mode
    if body.stop_mode == PtScriptStopMode.DURATION.value:
        script.duration_seconds = body.duration_seconds
    else:
        script.duration_seconds = None
        script.default_max_requests = body.default_max_requests or script.default_max_requests
    script.sampler_limits_json = body.sampler_limits
    script.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(script)
    return _to_pt_script_response(script)


@router.post("/upload", response_model=PtScriptUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pt_script(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PtScriptUploadResponse:
    scenario = get_pt_scenario_or_404(project_id, scenario_id, db)
    script = scenario.script
    if script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Performance script not found",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    content = await file.read()
    previous_path = script.file_path

    try:
        resolve_file_type(file.filename)
        parsed_plan = parse_jmx_content(content)
        saved_path, file_size = save_pt_jmx_upload(
            pt_project_id=project_id,
            filename=file.filename,
            content=content,
        )
        script.filename = file.filename
        script.file_path = str(saved_path)
        script.file_size = file_size
        script.parse_status = PtScriptParseStatus.SUCCESS.value
        script.parse_error = None
        script.parsed_plan_json = parsed_plan.to_json()
        script.uploaded_at = datetime.now(timezone.utc)
    except UnsupportedPtJmxFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PtJmxSizeLimitError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PtJmxParseError as exc:
        script.filename = file.filename
        script.file_size = len(content)
        script.file_path = None
        script.parse_status = PtScriptParseStatus.FAILED.value
        script.parse_error = str(exc)
        script.parsed_plan_json = None
        script.uploaded_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(script)
        return PtScriptUploadResponse(script=_to_pt_script_response(script))

    db.commit()
    delete_pt_jmx_file(previous_path)
    db.refresh(script)
    return PtScriptUploadResponse(script=_to_pt_script_response(script))

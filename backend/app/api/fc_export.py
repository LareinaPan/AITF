import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.fc_projects import get_fc_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_test_case import FcTestCase
from app.models.user import User
from app.schemas.fc_experience_case import FC_CASE_TYPES
from app.services.fc_exporter import (
    ExportableFcCase,
    FcExportError,
    export_cases_to_excel,
    export_cases_to_xmind,
    safe_export_filename,
)

router = APIRouter()


def _load_export_cases(
    fc_project_id: uuid.UUID,
    db: Session,
    *,
    status_filter: str,
    module: str | None,
    case_type: str | None,
    generation_batch_id: uuid.UUID | None,
    no_batch: bool,
) -> list[ExportableFcCase]:
    query = select(FcTestCase).where(FcTestCase.fc_project_id == fc_project_id)
    query = query.where(FcTestCase.status == status_filter)

    if module is not None:
        query = query.where(FcTestCase.module == module.strip())
    if case_type is not None:
        query = query.where(FcTestCase.case_type == case_type)
    if no_batch:
        query = query.where(FcTestCase.generation_batch_id.is_(None))
    elif generation_batch_id is not None:
        query = query.where(FcTestCase.generation_batch_id == generation_batch_id)

    rows = list(db.scalars(query.order_by(FcTestCase.module.asc(), FcTestCase.case_no.asc())).all())
    return [
        ExportableFcCase(
            case_no=row.case_no,
            module=row.module,
            title=row.title,
            preconditions=row.preconditions,
            steps=row.steps,
            expected_result=row.expected_result,
            priority=row.priority,
            case_type=row.case_type,
        )
        for row in rows
    ]


def _validate_export_filters(
    status_filter: str,
    case_type: str | None,
) -> None:
    if status_filter not in {"active", "draft"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter",
        )
    if case_type is not None and case_type not in FC_CASE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case_type filter: {case_type}",
        )


def _build_content_disposition(project_name: str, suffix: str) -> str:
    ascii_filename = safe_export_filename(project_name, suffix)
    display_filename = f"{project_name.strip()}{suffix}" if project_name.strip() else ascii_filename
    disposition = f'attachment; filename="{ascii_filename}"'
    if display_filename != ascii_filename:
        disposition = f'{disposition}; filename*=UTF-8\'\'{quote(display_filename)}'
    return disposition


def _stream_file(
    content: bytes,
    *,
    project_name: str,
    suffix: str,
    media_type: str,
) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": _build_content_disposition(project_name, suffix)},
    )


@router.get("/excel")
def export_fc_cases_excel(
    fc_project_id: uuid.UUID,
    status_filter: str = Query(default="active", alias="status"),
    module: str | None = Query(default=None),
    case_type: str | None = Query(default=None),
    generation_batch_id: uuid.UUID | None = Query(default=None),
    no_batch: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    project = get_fc_project_or_404(fc_project_id, db)
    _validate_export_filters(status_filter, case_type)

    cases = _load_export_cases(
        fc_project_id,
        db,
        status_filter=status_filter,
        module=module,
        case_type=case_type,
        generation_batch_id=generation_batch_id,
        no_batch=no_batch,
    )
    try:
        content = export_cases_to_excel(cases, project_name=project.name)
    except FcExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _stream_file(
        content,
        project_name=project.name,
        suffix=".xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/xmind")
def export_fc_cases_xmind(
    fc_project_id: uuid.UUID,
    status_filter: str = Query(default="active", alias="status"),
    module: str | None = Query(default=None),
    case_type: str | None = Query(default=None),
    generation_batch_id: uuid.UUID | None = Query(default=None),
    no_batch: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    project = get_fc_project_or_404(fc_project_id, db)
    _validate_export_filters(status_filter, case_type)

    cases = _load_export_cases(
        fc_project_id,
        db,
        status_filter=status_filter,
        module=module,
        case_type=case_type,
        generation_batch_id=generation_batch_id,
        no_batch=no_batch,
    )
    try:
        content = export_cases_to_xmind(cases, project_name=project.name)
    except FcExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _stream_file(
        content,
        project_name=project.name,
        suffix=".xmind",
        media_type="application/vnd.xmind.workbook",
    )

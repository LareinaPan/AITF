import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.fc_projects import get_fc_project_or_404
from app.config import PROJECT_ROOT
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_experience_case import FcExperienceCase
from app.models.user import User
from app.schemas.fc_experience_case import (
    FC_CASE_TYPES,
    FC_PRIORITIES,
    FcExperienceCaseCreateRequest,
    FcExperienceCaseListResponse,
    FcExperienceCaseResponse,
    FcExperienceCaseUpdateRequest,
    FcExperienceImportResponse,
)
from app.services.fc_experience_importer import (
    FcExperienceImportError,
    parse_experience_case_excel,
)

router = APIRouter()

TEMPLATE_PATH = PROJECT_ROOT / "docs" / "templates" / "fc-case-template.xlsx"


def _to_response(case: FcExperienceCase) -> FcExperienceCaseResponse:
    return FcExperienceCaseResponse.model_validate(case)


def _get_case_or_404(case_id: uuid.UUID, db: Session) -> FcExperienceCase:
    case = db.get(FcExperienceCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experience case not found",
        )
    return case


def _ensure_case_belongs_to_project(case: FcExperienceCase, fc_project_id: uuid.UUID) -> None:
    if case.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experience case not found",
        )


def _validate_enums(priority: str, case_type: str) -> None:
    if priority not in FC_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority: {priority}",
        )
    if case_type not in FC_CASE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case_type: {case_type}",
        )


@router.get("", response_model=FcExperienceCaseListResponse)
def list_experience_cases(
    fc_project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcExperienceCaseListResponse:
    get_fc_project_or_404(fc_project_id, db)

    total = db.scalar(
        select(func.count())
        .select_from(FcExperienceCase)
        .where(FcExperienceCase.fc_project_id == fc_project_id)
    )
    assert total is not None

    offset = (page - 1) * page_size
    cases = list(
        db.scalars(
            select(FcExperienceCase)
            .where(FcExperienceCase.fc_project_id == fc_project_id)
            .order_by(FcExperienceCase.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    return FcExperienceCaseListResponse(
        items=[_to_response(case) for case in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=FcExperienceCaseResponse, status_code=status.HTTP_201_CREATED)
def create_experience_case(
    fc_project_id: uuid.UUID,
    payload: FcExperienceCaseCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcExperienceCaseResponse:
    get_fc_project_or_404(fc_project_id, db)
    _validate_enums(payload.priority, payload.case_type)

    case = FcExperienceCase(
        fc_project_id=fc_project_id,
        case_no=payload.case_no,
        module=payload.module.strip(),
        title=payload.title.strip(),
        preconditions=payload.preconditions,
        steps=payload.steps.strip(),
        expected_result=payload.expected_result.strip(),
        priority=payload.priority,
        case_type=payload.case_type,
        tags=payload.tags,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return _to_response(case)


@router.get("/import-template")
def download_import_template(
    fc_project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FileResponse:
    get_fc_project_or_404(fc_project_id, db)
    if not TEMPLATE_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import template file not found",
        )
    return FileResponse(
        path=TEMPLATE_PATH,
        filename="fc-case-template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/import", response_model=FcExperienceImportResponse, status_code=status.HTTP_201_CREATED)
async def import_experience_cases(
    fc_project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcExperienceImportResponse:
    get_fc_project_or_404(fc_project_id, db)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload filename is required",
        )

    if Path(file.filename).suffix.lower() != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .xlsx 格式的 Excel 文件",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload file is empty",
        )

    try:
        parsed = parse_experience_case_excel(content)
    except FcExperienceImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    created_cases: list[FcExperienceCase] = []
    for row in parsed.valid_rows:
        case = FcExperienceCase(
            fc_project_id=fc_project_id,
            case_no=row.case_no,
            module=row.module,
            title=row.title,
            preconditions=row.preconditions,
            steps=row.steps,
            expected_result=row.expected_result,
            priority=row.priority,
            case_type=row.case_type,
        )
        db.add(case)
        created_cases.append(case)

    db.commit()
    for case in created_cases:
        db.refresh(case)

    return FcExperienceImportResponse(
        imported_count=len(created_cases),
        rejected_count=len(parsed.errors),
        errors=parsed.errors,
        cases=[_to_response(case) for case in created_cases],
    )


@router.put("/{case_id}", response_model=FcExperienceCaseResponse)
def update_experience_case(
    fc_project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: FcExperienceCaseUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcExperienceCaseResponse:
    get_fc_project_or_404(fc_project_id, db)
    case = _get_case_or_404(case_id, db)
    _ensure_case_belongs_to_project(case, fc_project_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field in ("module", "title", "steps", "expected_result"):
        if field in update_data and update_data[field] is not None:
            update_data[field] = update_data[field].strip()

    priority = update_data.get("priority", case.priority)
    case_type = update_data.get("case_type", case.case_type)
    _validate_enums(priority, case_type)

    for field, value in update_data.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    return _to_response(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience_case(
    fc_project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_fc_project_or_404(fc_project_id, db)
    case = _get_case_or_404(case_id, db)
    _ensure_case_belongs_to_project(case, fc_project_id)
    db.delete(case)
    db.commit()

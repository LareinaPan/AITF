import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.fc_projects import get_fc_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_requirement_doc import FcRequirementDoc, FcRequirementParseStatus
from app.models.user import User
from app.schemas.fc_requirement_doc import (
    FcRequirementDocDetailResponse,
    FcRequirementDocResponse,
    FcRequirementDocUploadResponse,
)
from app.services.fc_doc_parser import (
    FcDocParseError,
    FcDocSizeLimitError,
    UnsupportedFcDocFormatError,
    delete_fc_requirement_file,
    parse_requirement_content,
    resolve_file_type,
    save_fc_requirement_upload,
)
from app.config import get_settings

router = APIRouter()

PARSED_TEXT_PREVIEW_LENGTH = 500


def _build_preview(parsed_text: str | None) -> str | None:
    if not parsed_text:
        return None
    if len(parsed_text) <= PARSED_TEXT_PREVIEW_LENGTH:
        return parsed_text
    return parsed_text[:PARSED_TEXT_PREVIEW_LENGTH] + "..."


def _to_doc_response(doc: FcRequirementDoc) -> FcRequirementDocResponse:
    uploader_name = doc.uploader.username if doc.uploader is not None else "未知用户"
    return FcRequirementDocResponse(
        id=doc.id,
        fc_project_id=doc.fc_project_id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        parse_status=doc.parse_status,
        parse_error=doc.parse_error,
        parsed_text_preview=_build_preview(doc.parsed_text),
        uploaded_by=doc.uploaded_by,
        uploaded_by_username=uploader_name,
        created_at=doc.created_at,
    )


def _load_doc_with_uploader(doc_id: uuid.UUID, db: Session) -> FcRequirementDoc:
    doc = db.scalar(
        select(FcRequirementDoc)
        .where(FcRequirementDoc.id == doc_id)
        .options(selectinload(FcRequirementDoc.uploader))
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement document not found",
        )
    return doc


def _ensure_doc_belongs_to_project(
    doc: FcRequirementDoc,
    fc_project_id: uuid.UUID,
) -> None:
    if doc.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement document not found",
        )


def _count_project_docs(fc_project_id: uuid.UUID, db: Session) -> int:
    return db.scalar(
        select(func.count())
        .select_from(FcRequirementDoc)
        .where(FcRequirementDoc.fc_project_id == fc_project_id)
    ) or 0


@router.get("", response_model=list[FcRequirementDocResponse])
def list_requirement_docs(
    fc_project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FcRequirementDocResponse]:
    get_fc_project_or_404(fc_project_id, db)
    docs = list(
        db.scalars(
            select(FcRequirementDoc)
            .where(FcRequirementDoc.fc_project_id == fc_project_id)
            .options(selectinload(FcRequirementDoc.uploader))
            .order_by(FcRequirementDoc.created_at.desc())
        ).all()
    )
    return [_to_doc_response(doc) for doc in docs]


@router.post("/upload", response_model=FcRequirementDocUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_requirement_doc(
    fc_project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FcRequirementDocUploadResponse:
    get_fc_project_or_404(fc_project_id, db)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload filename is required",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload file is empty",
        )

    max_docs = get_settings().fc_max_docs_per_project
    if _count_project_docs(fc_project_id, db) >= max_docs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project document limit reached ({max_docs})",
        )

    try:
        saved_path = save_fc_requirement_upload(fc_project_id, file.filename, content)
        file_type = resolve_file_type(file.filename)
    except (UnsupportedFcDocFormatError, FcDocSizeLimitError, FcDocParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        parsed_text = parse_requirement_content(content, file.filename)
        parse_status = FcRequirementParseStatus.SUCCESS.value
        parse_error: str | None = None
    except FcDocParseError as exc:
        parsed_text = None
        parse_status = FcRequirementParseStatus.FAILED.value
        parse_error = str(exc)

    doc = FcRequirementDoc(
        fc_project_id=fc_project_id,
        filename=file.filename,
        file_path=str(saved_path),
        file_type=file_type,
        file_size=len(content),
        parsed_text=parsed_text,
        parse_status=parse_status,
        parse_error=parse_error,
        uploaded_by=current_user.id,
    )
    db.add(doc)
    db.commit()
    return FcRequirementDocUploadResponse(doc=_to_doc_response(_load_doc_with_uploader(doc.id, db)))


@router.get("/{doc_id}", response_model=FcRequirementDocDetailResponse)
def get_requirement_doc(
    fc_project_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcRequirementDocDetailResponse:
    get_fc_project_or_404(fc_project_id, db)
    doc = _load_doc_with_uploader(doc_id, db)
    _ensure_doc_belongs_to_project(doc, fc_project_id)
    response = _to_doc_response(doc)
    return FcRequirementDocDetailResponse(
        **response.model_dump(),
        parsed_text=doc.parsed_text,
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement_doc(
    fc_project_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_fc_project_or_404(fc_project_id, db)
    doc = _load_doc_with_uploader(doc_id, db)
    _ensure_doc_belongs_to_project(doc, fc_project_id)
    delete_fc_requirement_file(doc.file_path)
    db.delete(doc)
    db.commit()

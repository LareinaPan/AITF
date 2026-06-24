import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.projects import get_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.api_endpoint import OpenAPIUploadResponse
from app.services.api_endpoint_service import upsert_parsed_endpoints
from app.services.openapi_parser import (
    OpenAPIParseError,
    UnsupportedOpenAPIFormatError,
    parse_openapi_content,
    save_openapi_upload,
)

router = APIRouter()


@router.post("/upload", response_model=OpenAPIUploadResponse)
async def upload_openapi(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> OpenAPIUploadResponse:
    get_project_or_404(project_id, db)

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

    try:
        save_openapi_upload(project_id, file.filename, content)
        endpoints = parse_openapi_content(content, file.filename)
        result = upsert_parsed_endpoints(db, project_id, endpoints)
        db.commit()
    except UnsupportedOpenAPIFormatError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OpenAPIParseError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return OpenAPIUploadResponse(
        filename=file.filename,
        created=result.created,
        updated=result.updated,
        total=result.created + result.updated,
    )

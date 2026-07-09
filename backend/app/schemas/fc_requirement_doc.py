import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FcRequirementDocResponse(BaseModel):
    id: uuid.UUID
    fc_project_id: uuid.UUID
    filename: str
    file_type: str
    file_size: int
    parse_status: str
    parse_error: str | None
    parsed_text_preview: str | None = Field(
        default=None,
        description="First 500 characters of parsed text",
    )
    uploaded_by: uuid.UUID
    uploaded_by_username: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FcRequirementDocDetailResponse(FcRequirementDocResponse):
    parsed_text: str | None = None


class FcRequirementDocUploadResponse(BaseModel):
    doc: FcRequirementDocResponse

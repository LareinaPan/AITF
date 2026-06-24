import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiEndpointResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    method: str
    path: str
    summary: str | None
    description: str | None
    parameters_json: list[Any]
    request_body_json: dict[str, Any] | None
    responses_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiEndpointListItemResponse(ApiEndpointResponse):
    test_case_count: int = Field(default=0, ge=0)


class ApiEndpointListResponse(BaseModel):
    items: list[ApiEndpointListItemResponse]
    total: int
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)


class OpenAPIUploadResponse(BaseModel):
    filename: str
    created: int = Field(..., ge=0)
    updated: int = Field(..., ge=0)
    total: int = Field(..., ge=0)


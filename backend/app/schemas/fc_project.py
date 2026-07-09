import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FcProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class FcProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class FcProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    created_by_username: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FcProjectStatsResponse(BaseModel):
    doc_count: int
    experience_case_count: int
    active_case_count: int
    draft_case_count: int
    batch_count: int
    last_batch_at: datetime | None

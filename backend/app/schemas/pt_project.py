import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PtProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class PtProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class PtProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    created_by_username: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PtProjectStatsResponse(BaseModel):
    scenario_count: int
    run_count: int
    last_run_at: datetime | None
    last_run_status: str | None

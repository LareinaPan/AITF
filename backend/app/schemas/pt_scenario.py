import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PtScenarioCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class PtScenarioUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class PtScenarioResponse(BaseModel):
    id: uuid.UUID
    pt_project_id: uuid.UUID
    name: str
    description: str | None
    script_id: uuid.UUID
    parse_status: str
    last_run_status: str | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

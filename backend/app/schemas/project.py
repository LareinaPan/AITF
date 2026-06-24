import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    feishu_webhook_url: str | None = Field(default=None, max_length=512)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    feishu_webhook_url: str | None = Field(default=None, max_length=512)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    feishu_webhook_url: str | None
    created_by: uuid.UUID
    created_by_username: str
    created_at: datetime

    model_config = {"from_attributes": True}

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FC_PRIORITIES = ("P0", "P1", "P2", "P3")
FC_CASE_TYPES = (
    "positive",
    "negative",
    "boundary",
    "permission",
    "security",
    "compatibility",
)

FcPriority = Literal["P0", "P1", "P2", "P3"]
FcCaseType = Literal[
    "positive",
    "negative",
    "boundary",
    "permission",
    "security",
    "compatibility",
]


class FcExperienceCaseCreateRequest(BaseModel):
    case_no: str | None = Field(default=None, max_length=64)
    module: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=256)
    preconditions: str | None = Field(default=None, max_length=4000)
    steps: str = Field(..., min_length=1, max_length=8000)
    expected_result: str = Field(..., min_length=1, max_length=8000)
    priority: FcPriority = "P2"
    case_type: FcCaseType = "positive"
    tags: str | None = Field(default=None, max_length=256)

    @field_validator("case_no", "module", "title", "preconditions", "steps", "expected_result", "tags")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FcExperienceCaseUpdateRequest(BaseModel):
    case_no: str | None = Field(default=None, max_length=64)
    module: str | None = Field(default=None, min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    preconditions: str | None = Field(default=None, max_length=4000)
    steps: str | None = Field(default=None, min_length=1, max_length=8000)
    expected_result: str | None = Field(default=None, min_length=1, max_length=8000)
    priority: FcPriority | None = None
    case_type: FcCaseType | None = None
    tags: str | None = Field(default=None, max_length=256)


class FcExperienceCaseResponse(BaseModel):
    id: uuid.UUID
    fc_project_id: uuid.UUID
    case_no: str | None
    module: str
    title: str
    preconditions: str | None
    steps: str
    expected_result: str
    priority: str
    case_type: str
    tags: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FcExperienceCaseListResponse(BaseModel):
    items: list[FcExperienceCaseResponse]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)


class FcExperienceImportResponse(BaseModel):
    imported_count: int
    rejected_count: int
    errors: list[str]
    cases: list[FcExperienceCaseResponse]

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.fc_experience_case import FcCaseType, FcPriority


class FcTestCaseCreateRequest(BaseModel):
    case_no: str | None = Field(default=None, max_length=64)
    module: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=256)
    preconditions: str | None = Field(default=None, max_length=4000)
    steps: str = Field(..., min_length=1, max_length=8000)
    expected_result: str = Field(..., min_length=1, max_length=8000)
    priority: FcPriority = "P2"
    case_type: FcCaseType = "positive"
    status: str = Field(default="draft", pattern="^(draft|active)$")
    requirement_doc_id: uuid.UUID | None = None
    generation_batch_id: uuid.UUID | None = None

    @field_validator(
        "case_no",
        "module",
        "title",
        "preconditions",
        "steps",
        "expected_result",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FcTestCaseUpdateRequest(BaseModel):
    case_no: str | None = Field(default=None, min_length=1, max_length=64)
    module: str | None = Field(default=None, min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    preconditions: str | None = Field(default=None, max_length=4000)
    steps: str | None = Field(default=None, min_length=1, max_length=8000)
    expected_result: str | None = Field(default=None, min_length=1, max_length=8000)
    priority: FcPriority | None = None
    case_type: FcCaseType | None = None
    status: str | None = Field(default=None, pattern="^(draft|active)$")


class FcTestCaseBatchDeleteRequest(BaseModel):
    case_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)


class FcTestCaseBatchDeleteResponse(BaseModel):
    deleted_count: int


class FcTestCaseResponse(BaseModel):
    id: uuid.UUID
    fc_project_id: uuid.UUID
    requirement_doc_id: uuid.UUID | None
    generation_batch_id: uuid.UUID | None
    case_no: str
    module: str
    title: str
    preconditions: str | None
    steps: str
    expected_result: str
    priority: str
    case_type: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FcTestCaseListResponse(BaseModel):
    items: list[FcTestCaseResponse]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)


class FcTestCaseFilterOptionsResponse(BaseModel):
    modules: list[str]
    generation_batch_ids: list[uuid.UUID]
    has_no_batch: bool

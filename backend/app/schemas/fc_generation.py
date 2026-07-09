import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.fc_experience_case import FC_CASE_TYPES, FC_PRIORITIES, FcCaseType, FcPriority


class FcAIGeneratedCaseCandidate(BaseModel):
    case_no: str | None = Field(default=None, max_length=64)
    module: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=256)
    preconditions: str | None = Field(default=None, max_length=4000)
    steps: str = Field(..., min_length=1, max_length=8000)
    expected_result: str = Field(..., min_length=1, max_length=8000)
    priority: FcPriority = "P2"
    case_type: FcCaseType = "positive"

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

    def to_storage_dict(self, *, default_case_no: str | None = None) -> dict[str, Any]:
        case_no = self.case_no or default_case_no or "FC-001"
        return {
            "case_no": case_no,
            "module": self.module.strip(),
            "title": self.title.strip(),
            "preconditions": self.preconditions,
            "steps": self.steps.strip(),
            "expected_result": self.expected_result.strip(),
            "priority": self.priority,
            "case_type": self.case_type,
        }


class FcGenerateRequest(BaseModel):
    requirement_doc_id: uuid.UUID
    experience_case_ids: list[uuid.UUID] = Field(default_factory=list)
    user_feedback: str | None = Field(default=None, max_length=2000)
    parent_batch_id: uuid.UUID | None = None


class FcGenerateResponse(BaseModel):
    batch_id: uuid.UUID
    status: str


class FcBatchConfirmRequest(BaseModel):
    case_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Empty list confirms all draft cases in the batch",
    )


class FcBatchConfirmResponse(BaseModel):
    confirmed_count: int
    batch_status: str


class FcBatchRejectRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=2000)


class FcBatchRejectResponse(BaseModel):
    batch_id: uuid.UUID
    status: str
    parent_batch_id: uuid.UUID


class FcFeatureChecklistItem(BaseModel):
    feature: str = Field(..., min_length=1, max_length=256)
    covered: bool
    case_count: int = Field(default=0, ge=0)


class FcAIReviewReport(BaseModel):
    coverage_score: float = Field(..., ge=0, le=100)
    dimension_scores: dict[str, float]
    feature_checklist: list[FcFeatureChecklistItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    passed: bool

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimension_scores(cls, value: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key in FC_CASE_TYPES:
            score = value.get(key, 0.0)
            try:
                normalized[key] = float(max(0.0, min(100.0, score)))
            except (TypeError, ValueError):
                normalized[key] = 0.0
        return normalized

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "coverage_score": self.coverage_score,
            "dimension_scores": self.dimension_scores,
            "feature_checklist": [item.model_dump() for item in self.feature_checklist],
            "gaps": self.gaps,
            "suggestions": self.suggestions,
            "passed": self.passed,
        }


class FcGenerationBatchResponse(BaseModel):
    id: uuid.UUID
    fc_project_id: uuid.UUID
    requirement_doc_id: uuid.UUID
    experience_case_ids: list[str]
    status: str
    coverage_score: float | None
    review_report_json: dict[str, Any] | None
    user_feedback: str | None
    internal_retry_count: int
    parent_batch_id: uuid.UUID | None
    triggered_by: uuid.UUID
    triggered_by_username: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    case_count: int = Field(default=0, description="Number of test cases in this batch")

    model_config = {"from_attributes": True}

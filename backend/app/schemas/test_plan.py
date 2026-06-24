import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.cron_validator import (
    CronExpressionError,
    normalize_cron_expression,
    validate_enabled_cron,
)


class TestPlanCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    environment_id: uuid.UUID
    cron_expression: str | None = Field(default=None, max_length=128)
    is_enabled: bool = False
    notify_on_complete: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, value: str | None) -> str | None:
        try:
            return normalize_cron_expression(value)
        except CronExpressionError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_schedule(self) -> "TestPlanCreateRequest":
        try:
            validate_enabled_cron(
                is_enabled=self.is_enabled,
                cron_expression=self.cron_expression,
            )
        except CronExpressionError as exc:
            raise ValueError(str(exc)) from exc
        return self


class TestPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    environment_id: uuid.UUID | None = None
    cron_expression: str | None = Field(default=None, max_length=128)
    is_enabled: bool | None = None
    notify_on_complete: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, value: str | None) -> str | None:
        try:
            return normalize_cron_expression(value)
        except CronExpressionError as exc:
            raise ValueError(str(exc)) from exc


class PlanCaseItemResponse(BaseModel):
    case_id: uuid.UUID
    case_name: str
    sort_order: int
    status: str

    model_config = {"from_attributes": True}


class TestPlanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    cron_expression: str | None
    environment_id: uuid.UUID
    environment_name: str
    is_enabled: bool
    notify_on_complete: bool
    created_at: datetime
    case_count: int = 0

    model_config = {"from_attributes": True}


class TestPlanDetailResponse(TestPlanResponse):
    cases: list[PlanCaseItemResponse] = Field(default_factory=list)


class PlanCaseBindRequest(BaseModel):
    case_ids: list[uuid.UUID] = Field(..., min_length=1)


class PlanRunResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    total_count: int
    pass_count: int
    fail_count: int
    allure_report_url: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

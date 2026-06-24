from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.test_case import (
    VALID_PRIORITIES,
    AssertionsJsonSchema,
    RequestJsonSchema,
    TestCaseResponse,
)


class ContainsBodyRuleSchema(BaseModel):
    type: Literal["contains"]
    value: str = Field(..., min_length=1, max_length=2048)


class JsonPathBodyRuleSchema(BaseModel):
    type: Literal["json_path"]
    path: str = Field(..., min_length=1, max_length=256)
    operator: Literal["eq"] = "eq"
    expected: str = Field(..., min_length=1, max_length=2048)


class AIGeneratedAssertionsSchema(AssertionsJsonSchema):
    body_rules: list[ContainsBodyRuleSchema | JsonPathBodyRuleSchema] = Field(default_factory=list)


class AIGeneratedTestCaseCandidate(BaseModel):
    """Schema for a single LLM-generated test case candidate."""

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    priority: str = "P2"
    request_json: RequestJsonSchema
    assertions_json: AIGeneratedAssertionsSchema

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        request_json = normalized.get("request_json")
        if isinstance(request_json, dict):
            request_copy = dict(request_json)
            if "method" in request_copy and isinstance(request_copy["method"], str):
                request_copy["method"] = request_copy["method"].strip().upper()
            normalized["request_json"] = request_copy
        return normalized

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "request_json": self.request_json.model_dump(),
            "assertions_json": self.assertions_json.model_dump(),
        }


class AIGenerateRequest(BaseModel):
    positive_count: int = Field(default=0, ge=0, le=10)
    boundary_count: int = Field(default=0, ge=0, le=10)
    exception_count: int = Field(default=0, ge=0, le=10)
    auth_count: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        total = (
            self.positive_count
            + self.boundary_count
            + self.exception_count
            + self.auth_count
        )
        if total <= 0:
            raise ValueError("At least one test case must be requested")
        if total > 20:
            raise ValueError("Cannot generate more than 20 test cases at once")
        return self


class AIGenerateResponse(BaseModel):
    cases: list[TestCaseResponse]
    requested_count: int = Field(..., ge=1)
    rejected_count: int = Field(default=0, ge=0)
    raw_count: int = Field(default=0, ge=0)


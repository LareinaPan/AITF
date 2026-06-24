import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
VALID_STATUSES = frozenset({"draft", "active"})
VALID_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
VALID_BODY_TYPES = frozenset({"none", "json", "raw", "form"})


class HeaderItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(default="", max_length=2048)


class QueryItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(default="", max_length=2048)


class RequestBodySchema(BaseModel):
    type: Literal["none", "json", "raw", "form"] = "none"
    content: str = Field(default="", max_length=10000)


class RequestJsonSchema(BaseModel):
    method: str = "GET"
    url: str = Field(default="", max_length=2048)
    headers: list[HeaderItem] = Field(default_factory=list)
    query: list[QueryItem] = Field(default_factory=list)
    body: RequestBodySchema = Field(default_factory=RequestBodySchema)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in VALID_HTTP_METHODS:
            raise ValueError(f"method must be one of {sorted(VALID_HTTP_METHODS)}")
        return normalized


class AssertionsJsonSchema(BaseModel):
    status_code: int = Field(default=200, ge=100, le=599)
    max_response_time_ms: int = Field(default=3000, ge=0, le=300000)
    body_rules: list[dict[str, Any]] = Field(default_factory=list)


class TestCaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    priority: str = "P2"
    status: str = "active"
    request_json: RequestJsonSchema | None = None
    assertions_json: AssertionsJsonSchema | None = None
    api_endpoint_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return value


class TestCaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    priority: str | None = None
    status: str | None = None
    request_json: RequestJsonSchema | None = None
    assertions_json: AssertionsJsonSchema | None = None
    api_endpoint_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip()

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return value


class TestCaseResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    request_json: dict[str, Any]
    assertions_json: dict[str, Any]
    priority: str
    status: str
    api_endpoint_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestCaseRunRequest(BaseModel):
    environment_id: uuid.UUID


class PreparedRequestResponse(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    body_type: str
    body_content: str


class HttpResponseResponse(BaseModel):
    status_code: int
    body: str
    elapsed_ms: float


class AssertionCheckResponse(BaseModel):
    name: str
    passed: bool
    message: str
    rule_type: str | None = None


class AssertionsEvaluationResponse(BaseModel):
    passed: bool
    checks: list[AssertionCheckResponse]


class TestCaseRunResponse(BaseModel):
    case_id: uuid.UUID
    case_name: str
    environment_id: uuid.UUID
    environment_name: str
    passed: bool
    error: str | None
    prepared_request: PreparedRequestResponse
    response: HttpResponseResponse | None
    assertions: AssertionsEvaluationResponse | None

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import get_settings


class ParsedSamplerHeaderSchema(BaseModel):
    name: str
    value: str


class ParsedSamplerSchema(BaseModel):
    key: str
    name: str
    method: str
    url: str
    headers: list[ParsedSamplerHeaderSchema] = Field(default_factory=list)
    has_variables: bool = False
    thread_group_name: str | None = None


class ParsedThreadGroupSchema(BaseModel):
    name: str
    num_threads: int | None = None
    ramp_time: int | None = None


class ParsedJmxPlanSchema(BaseModel):
    thread_groups: list[ParsedThreadGroupSchema] = Field(default_factory=list)
    samplers: list[ParsedSamplerSchema] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)


class PtScriptResponse(BaseModel):
    id: uuid.UUID
    pt_scenario_id: uuid.UUID
    filename: str | None
    file_size: int | None
    parse_status: str
    parse_error: str | None
    parsed_plan: ParsedJmxPlanSchema | None
    sampler_count: int
    thread_group_count: int
    max_concurrency: int
    ramp_up_seconds: int
    stop_mode: str
    duration_seconds: int | None
    default_max_requests: int
    sampler_limits: dict[str, int] | None
    uploaded_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PtScriptUploadResponse(BaseModel):
    script: PtScriptResponse


class PtScriptConfigUpdate(BaseModel):
    max_concurrency: int = Field(ge=1)
    ramp_up_seconds: int = Field(ge=0)
    stop_mode: Literal["request_limit", "duration"]
    duration_seconds: int | None = None
    default_max_requests: int | None = None
    sampler_limits: dict[str, int] | None = None

    @field_validator("sampler_limits")
    @classmethod
    def validate_sampler_limit_values(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        for sampler_key, limit in value.items():
            if limit < 1:
                raise ValueError(f"sampler_limits[{sampler_key!r}] must be >= 1")
        return value

    @model_validator(mode="after")
    def validate_stop_mode_fields(self) -> Self:
        settings = get_settings()
        if self.max_concurrency > settings.pt_max_concurrency:
            raise ValueError(
                f"max_concurrency must be <= {settings.pt_max_concurrency}"
            )
        if self.stop_mode == "duration":
            if self.duration_seconds is None:
                raise ValueError("duration_seconds is required when stop_mode is duration")
            if not 10 <= self.duration_seconds <= 86400:
                raise ValueError("duration_seconds must be between 10 and 86400")
        else:
            if self.default_max_requests is None:
                raise ValueError(
                    "default_max_requests is required when stop_mode is request_limit"
                )
            if self.default_max_requests < 1:
                raise ValueError("default_max_requests must be >= 1")
        return self

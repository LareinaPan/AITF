import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PtRunActionResponse(BaseModel):
    run_id: uuid.UUID
    status: str


class PtRunListItemResponse(BaseModel):
    id: uuid.UUID
    pt_project_id: uuid.UUID
    pt_scenario_id: uuid.UUID
    scenario_name_snapshot: str
    status: str
    stop_reason: str | None
    triggered_by: uuid.UUID
    started_at: datetime
    ended_at: datetime | None


class PtRunResponse(PtRunListItemResponse):
    config_snapshot_json: dict[str, Any]
    summary_json: dict[str, Any] | None
    error_message: str | None


class PtRunListResponse(BaseModel):
    items: list[PtRunListItemResponse]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)


class PtRunMetricPointResponse(BaseModel):
    id: uuid.UUID
    sampler_key: str
    recorded_at: datetime
    qps: float
    avg_rt_ms: float
    rt_p95_ms: float | None
    rt_p99_ms: float | None
    error_rate_percent: float

    model_config = {"from_attributes": True}


class PtRunMetricsResponse(BaseModel):
    items: list[PtRunMetricPointResponse]


class PtRunErrorLogResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    sampler_key: str
    sampler_name: str
    status_code: int | None
    error_type: str
    message: str

    model_config = {"from_attributes": True}


class PtRunErrorLogListResponse(BaseModel):
    items: list[PtRunErrorLogResponse]
    total: int | None = Field(default=None, ge=0)
    page: int | None = Field(default=None, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=500)

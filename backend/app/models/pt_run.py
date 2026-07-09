import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class PtRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PtRunStopReason(str, enum.Enum):
    REQUEST_LIMIT_REACHED = "request_limit_reached"
    DURATION_REACHED = "duration_reached"
    MANUAL_CANCEL = "manual_cancel"
    ENGINE_ERROR = "engine_error"


class PtRun(Base):
    __tablename__ = "pt_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    pt_project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pt_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pt_scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pt_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PtRunStatus.RUNNING.value,
        index=True,
    )
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    config_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("PtProject", back_populates="runs")
    scenario = relationship("PtScenario", back_populates="runs")
    triggered_by_user = relationship("User")
    metric_points = relationship(
        "PtRunMetricPoint",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    error_logs = relationship(
        "PtRunErrorLog",
        back_populates="run",
        cascade="all, delete-orphan",
    )

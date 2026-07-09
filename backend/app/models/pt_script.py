import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class PtScriptParseStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PtScriptStopMode(str, enum.Enum):
    REQUEST_LIMIT = "request_limit"
    DURATION = "duration"


class PtScript(Base):
    __tablename__ = "pt_scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    pt_scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pt_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PtScriptParseStatus.PENDING.value,
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    ramp_up_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stop_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PtScriptStopMode.DURATION.value,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_max_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    sampler_limits_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executor_node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scenario = relationship("PtScenario", back_populates="script")

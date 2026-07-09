import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PtRunMetricPoint(Base):
    __tablename__ = "pt_run_metric_points"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    pt_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pt_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sampler_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    qps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_rt_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rt_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rt_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_rate_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    run = relationship("PtRun", back_populates="metric_points")

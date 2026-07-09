import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PtRunErrorLog(Base):
    __tablename__ = "pt_run_error_logs"

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
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sampler_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sampler_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    run = relationship("PtRun", back_populates="error_logs")

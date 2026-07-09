import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class FcGenerationBatchStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"


class FcGenerationBatch(Base):
    __tablename__ = "fc_generation_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    fc_project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("fc_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_doc_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("fc_requirement_docs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experience_case_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FcGenerationBatchStatus.PENDING.value,
    )
    coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("fc_generation_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("FcProject", back_populates="generation_batches")
    requirement_doc = relationship("FcRequirementDoc")
    trigger_user = relationship("User")
    parent_batch = relationship(
        "FcGenerationBatch",
        remote_side="FcGenerationBatch.id",
        foreign_keys=[parent_batch_id],
    )
    test_cases = relationship(
        "FcTestCase",
        back_populates="generation_batch",
        cascade="all, delete-orphan",
    )

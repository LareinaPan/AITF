import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FcTestCaseStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"


class FcTestCase(Base):
    __tablename__ = "fc_test_cases"

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
    requirement_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("fc_requirement_docs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generation_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("fc_generation_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    case_no: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    preconditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, default="positive")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=FcTestCaseStatus.DRAFT.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project = relationship("FcProject", back_populates="test_cases")
    requirement_doc = relationship("FcRequirementDoc")
    generation_batch = relationship("FcGenerationBatch", back_populates="test_cases")

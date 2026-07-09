import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FcExperienceCase(Base):
    __tablename__ = "fc_experience_cases"

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
    case_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    module: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    preconditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, default="positive")
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project = relationship("FcProject", back_populates="experience_cases")

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FcProject(Base):
    __tablename__ = "fc_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    creator = relationship("User")
    requirement_docs = relationship(
        "FcRequirementDoc",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    experience_cases = relationship(
        "FcExperienceCase",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    test_cases = relationship(
        "FcTestCase",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    generation_batches = relationship(
        "FcGenerationBatch",
        back_populates="project",
        cascade="all, delete-orphan",
    )

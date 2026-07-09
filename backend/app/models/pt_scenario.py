import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PtScenario(Base):
    __tablename__ = "pt_scenarios"

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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    project = relationship("PtProject", back_populates="scenarios")
    script = relationship(
        "PtScript",
        back_populates="scenario",
        uselist=False,
        cascade="all, delete-orphan",
    )
    runs = relationship(
        "PtRun",
        back_populates="scenario",
        cascade="all, delete-orphan",
    )

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

DEFAULT_PARAMETERS_JSON: list[Any] = []
DEFAULT_REQUEST_BODY_JSON: dict[str, Any] | None = None
DEFAULT_RESPONSES_JSON: dict[str, Any] = {}


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "method",
            "path",
            name="uq_api_endpoints_project_method_path",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[list[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_PARAMETERS_JSON.copy(),
    )
    request_body_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    responses_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_RESPONSES_JSON.copy(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project = relationship("Project", back_populates="api_endpoints")

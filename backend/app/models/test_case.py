import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

DEFAULT_REQUEST_JSON: dict[str, Any] = {
    "method": "GET",
    "url": "",
    "headers": [],
    "query": [],
    "body": {"type": "none", "content": ""},
}

DEFAULT_ASSERTIONS_JSON: dict[str, Any] = {
    "status_code": 200,
    "max_response_time_ms": 3000,
    "body_rules": [],
}


class TestCase(Base):
    __test__ = False
    __tablename__ = "test_cases"

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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_REQUEST_JSON.copy(),
    )
    assertions_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_ASSERTIONS_JSON.copy(),
    )
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    api_endpoint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project = relationship("Project", back_populates="test_cases")
    plan_cases = relationship("PlanCase", back_populates="test_case")

"""add_notify_on_complete_to_test_plans

Revision ID: c3a8f2b1d904
Revises: b7c2d1e4f908
Create Date: 2026-06-22 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a8f2b1d904"
down_revision: Union[str, None] = "b7c2d1e4f908"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_plans",
        sa.Column(
            "notify_on_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("test_plans", "notify_on_complete")

"""create pt_projects table

Revision ID: b8c9d0e1f234
Revises: a7b8c9d0e123
Create Date: 2026-07-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f234"
down_revision: Union[str, None] = "a7b8c9d0e123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pt_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pt_projects_created_by"), "pt_projects", ["created_by"], unique=False)
    op.create_index(op.f("ix_pt_projects_name"), "pt_projects", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pt_projects_name"), table_name="pt_projects")
    op.drop_index(op.f("ix_pt_projects_created_by"), table_name="pt_projects")
    op.drop_table("pt_projects")

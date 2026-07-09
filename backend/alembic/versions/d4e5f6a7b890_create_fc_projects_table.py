"""create fc_projects table

Revision ID: d4e5f6a7b890
Revises: c3a8f2b1d904
Create Date: 2026-06-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b890"
down_revision: Union[str, None] = "c3a8f2b1d904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fc_projects",
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
    op.create_index(op.f("ix_fc_projects_created_by"), "fc_projects", ["created_by"], unique=False)
    op.create_index(op.f("ix_fc_projects_name"), "fc_projects", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fc_projects_name"), table_name="fc_projects")
    op.drop_index(op.f("ix_fc_projects_created_by"), table_name="fc_projects")
    op.drop_table("fc_projects")

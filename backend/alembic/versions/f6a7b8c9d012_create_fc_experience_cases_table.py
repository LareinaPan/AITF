"""create fc_experience_cases table

Revision ID: f6a7b8c9d012
Revises: e5f6a7b8c901
Create Date: 2026-06-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d012"
down_revision: Union[str, None] = "e5f6a7b8c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fc_experience_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fc_project_id", sa.Uuid(), nullable=False),
        sa.Column("case_no", sa.String(length=64), nullable=True),
        sa.Column("module", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("preconditions", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fc_project_id"], ["fc_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fc_experience_cases_fc_project_id"),
        "fc_experience_cases",
        ["fc_project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fc_experience_cases_fc_project_id"), table_name="fc_experience_cases")
    op.drop_table("fc_experience_cases")

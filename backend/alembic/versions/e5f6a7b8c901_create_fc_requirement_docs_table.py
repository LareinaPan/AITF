"""create fc_requirement_docs table

Revision ID: e5f6a7b8c901
Revises: d4e5f6a7b890
Create Date: 2026-06-24 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c901"
down_revision: Union[str, None] = "d4e5f6a7b890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fc_requirement_docs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fc_project_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fc_project_id"], ["fc_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fc_requirement_docs_fc_project_id"),
        "fc_requirement_docs",
        ["fc_project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fc_requirement_docs_uploaded_by"),
        "fc_requirement_docs",
        ["uploaded_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fc_requirement_docs_uploaded_by"), table_name="fc_requirement_docs")
    op.drop_index(op.f("ix_fc_requirement_docs_fc_project_id"), table_name="fc_requirement_docs")
    op.drop_table("fc_requirement_docs")

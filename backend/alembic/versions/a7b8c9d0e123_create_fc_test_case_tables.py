"""create fc_generation_batches and fc_test_cases tables

Revision ID: a7b8c9d0e123
Revises: f6a7b8c9d012
Create Date: 2026-06-24 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e123"
down_revision: Union[str, None] = "f6a7b8c9d012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fc_generation_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fc_project_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_doc_id", sa.Uuid(), nullable=False),
        sa.Column("experience_case_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=True),
        sa.Column("review_report_json", sa.JSON(), nullable=True),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("internal_retry_count", sa.Integer(), nullable=False),
        sa.Column("parent_batch_id", sa.Uuid(), nullable=True),
        sa.Column("triggered_by", sa.Uuid(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["fc_project_id"], ["fc_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_doc_id"], ["fc_requirement_docs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_batch_id"], ["fc_generation_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fc_generation_batches_fc_project_id"),
        "fc_generation_batches",
        ["fc_project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fc_generation_batches_requirement_doc_id"),
        "fc_generation_batches",
        ["requirement_doc_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fc_generation_batches_parent_batch_id"),
        "fc_generation_batches",
        ["parent_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fc_generation_batches_triggered_by"),
        "fc_generation_batches",
        ["triggered_by"],
        unique=False,
    )

    op.create_table(
        "fc_test_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fc_project_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_doc_id", sa.Uuid(), nullable=True),
        sa.Column("generation_batch_id", sa.Uuid(), nullable=True),
        sa.Column("case_no", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("preconditions", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fc_project_id"], ["fc_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_batch_id"], ["fc_generation_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requirement_doc_id"], ["fc_requirement_docs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fc_test_cases_fc_project_id"), "fc_test_cases", ["fc_project_id"], unique=False)
    op.create_index(
        op.f("ix_fc_test_cases_generation_batch_id"),
        "fc_test_cases",
        ["generation_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fc_test_cases_requirement_doc_id"),
        "fc_test_cases",
        ["requirement_doc_id"],
        unique=False,
    )
    op.create_index(op.f("ix_fc_test_cases_status"), "fc_test_cases", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fc_test_cases_status"), table_name="fc_test_cases")
    op.drop_index(op.f("ix_fc_test_cases_requirement_doc_id"), table_name="fc_test_cases")
    op.drop_index(op.f("ix_fc_test_cases_generation_batch_id"), table_name="fc_test_cases")
    op.drop_index(op.f("ix_fc_test_cases_fc_project_id"), table_name="fc_test_cases")
    op.drop_table("fc_test_cases")

    op.drop_index(op.f("ix_fc_generation_batches_triggered_by"), table_name="fc_generation_batches")
    op.drop_index(op.f("ix_fc_generation_batches_parent_batch_id"), table_name="fc_generation_batches")
    op.drop_index(op.f("ix_fc_generation_batches_requirement_doc_id"), table_name="fc_generation_batches")
    op.drop_index(op.f("ix_fc_generation_batches_fc_project_id"), table_name="fc_generation_batches")
    op.drop_table("fc_generation_batches")

"""create_test_plan_tables

Revision ID: b7c2d1e4f908
Revises: 004909dc6f91
Create Date: 2026-06-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2d1e4f908"
down_revision: Union[str, None] = "004909dc6f91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("cron_expression", sa.String(length=128), nullable=True),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_test_plans_environment_id"), "test_plans", ["environment_id"], unique=False)
    op.create_index(op.f("ix_test_plans_project_id"), "test_plans", ["project_id"], unique=False)

    op.create_table(
        "plan_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "case_id", name="uq_plan_cases_plan_case"),
    )
    op.create_index(op.f("ix_plan_cases_case_id"), "plan_cases", ["case_id"], unique=False)
    op.create_index(op.f("ix_plan_cases_plan_id"), "plan_cases", ["plan_id"], unique=False)

    op.create_table(
        "plan_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("pass_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("allure_report_url", sa.String(length=512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_runs_plan_id"), "plan_runs", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_plan_runs_plan_id"), table_name="plan_runs")
    op.drop_table("plan_runs")
    op.drop_index(op.f("ix_plan_cases_plan_id"), table_name="plan_cases")
    op.drop_index(op.f("ix_plan_cases_case_id"), table_name="plan_cases")
    op.drop_table("plan_cases")
    op.drop_index(op.f("ix_test_plans_project_id"), table_name="test_plans")
    op.drop_index(op.f("ix_test_plans_environment_id"), table_name="test_plans")
    op.drop_table("test_plans")

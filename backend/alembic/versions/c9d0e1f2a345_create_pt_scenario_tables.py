"""create pt_scenarios and pt_scripts tables

Revision ID: c9d0e1f2a345
Revises: b8c9d0e1f234
Create Date: 2026-07-03 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a345"
down_revision: Union[str, None] = "b8c9d0e1f234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pt_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pt_project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["pt_project_id"], ["pt_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pt_scenarios_pt_project_id"),
        "pt_scenarios",
        ["pt_project_id"],
        unique=False,
    )

    op.create_table(
        "pt_scripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pt_scenario_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("parsed_plan_json", sa.JSON(), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("ramp_up_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_mode", sa.String(length=32), nullable=False, server_default="duration"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("default_max_requests", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("sampler_limits_json", sa.JSON(), nullable=True),
        sa.Column("executor_node_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["pt_scenario_id"], ["pt_scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pt_scenario_id"),
    )
    op.create_index(
        op.f("ix_pt_scripts_pt_scenario_id"),
        "pt_scripts",
        ["pt_scenario_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pt_scripts_pt_scenario_id"), table_name="pt_scripts")
    op.drop_table("pt_scripts")
    op.drop_index(op.f("ix_pt_scenarios_pt_project_id"), table_name="pt_scenarios")
    op.drop_table("pt_scenarios")

"""create pt_runs table

Revision ID: d0e1f2a3b456
Revises: c9d0e1f2a345
Create Date: 2026-07-08 04:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b456"
down_revision: Union[str, None] = "c9d0e1f2a345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pt_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pt_project_id", sa.Uuid(), nullable=False),
        sa.Column("pt_scenario_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_name_snapshot", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("config_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pt_project_id"], ["pt_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pt_scenario_id"], ["pt_scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pt_runs_pt_project_id"), "pt_runs", ["pt_project_id"], unique=False)
    op.create_index(op.f("ix_pt_runs_pt_scenario_id"), "pt_runs", ["pt_scenario_id"], unique=False)
    op.create_index(op.f("ix_pt_runs_status"), "pt_runs", ["status"], unique=False)
    op.create_index(op.f("ix_pt_runs_triggered_by"), "pt_runs", ["triggered_by"], unique=False)
    op.create_index(
        op.f("ix_pt_runs_pt_project_id_started_at"),
        "pt_runs",
        ["pt_project_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pt_runs_pt_project_id_started_at"), table_name="pt_runs")
    op.drop_index(op.f("ix_pt_runs_triggered_by"), table_name="pt_runs")
    op.drop_index(op.f("ix_pt_runs_status"), table_name="pt_runs")
    op.drop_index(op.f("ix_pt_runs_pt_scenario_id"), table_name="pt_runs")
    op.drop_index(op.f("ix_pt_runs_pt_project_id"), table_name="pt_runs")
    op.drop_table("pt_runs")

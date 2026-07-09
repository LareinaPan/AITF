"""create pt_run_metric_points and pt_run_error_logs tables

Revision ID: e1f2a3b4c567
Revises: d0e1f2a3b456
Create Date: 2026-07-08 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c567"
down_revision: Union[str, None] = "d0e1f2a3b456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pt_run_metric_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pt_run_id", sa.Uuid(), nullable=False),
        sa.Column("sampler_key", sa.String(length=128), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("qps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_rt_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rt_p95_ms", sa.Float(), nullable=True),
        sa.Column("rt_p99_ms", sa.Float(), nullable=True),
        sa.Column("error_rate_percent", sa.Float(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["pt_run_id"], ["pt_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pt_run_metric_points_pt_run_id"),
        "pt_run_metric_points",
        ["pt_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_run_metric_points_sampler_key"),
        "pt_run_metric_points",
        ["sampler_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_run_metric_points_pt_run_id_recorded_at"),
        "pt_run_metric_points",
        ["pt_run_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_run_metric_points_pt_run_id_sampler_key_recorded_at"),
        "pt_run_metric_points",
        ["pt_run_id", "sampler_key", "recorded_at"],
        unique=False,
    )

    op.create_table(
        "pt_run_error_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pt_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("sampler_key", sa.String(length=128), nullable=False),
        sa.Column("sampler_name", sa.String(length=256), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["pt_run_id"], ["pt_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pt_run_error_logs_pt_run_id"),
        "pt_run_error_logs",
        ["pt_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_run_error_logs_pt_run_id_occurred_at"),
        "pt_run_error_logs",
        ["pt_run_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pt_run_error_logs_pt_run_id_occurred_at"),
        table_name="pt_run_error_logs",
    )
    op.drop_index(op.f("ix_pt_run_error_logs_pt_run_id"), table_name="pt_run_error_logs")
    op.drop_table("pt_run_error_logs")

    op.drop_index(
        op.f("ix_pt_run_metric_points_pt_run_id_sampler_key_recorded_at"),
        table_name="pt_run_metric_points",
    )
    op.drop_index(
        op.f("ix_pt_run_metric_points_pt_run_id_recorded_at"),
        table_name="pt_run_metric_points",
    )
    op.drop_index(
        op.f("ix_pt_run_metric_points_sampler_key"),
        table_name="pt_run_metric_points",
    )
    op.drop_index(
        op.f("ix_pt_run_metric_points_pt_run_id"),
        table_name="pt_run_metric_points",
    )
    op.drop_table("pt_run_metric_points")

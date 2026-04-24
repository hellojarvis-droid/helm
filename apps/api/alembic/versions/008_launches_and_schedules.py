"""Business launches + launch steps + scheduled jobs

Revision ID: 008_launches_and_schedules
Revises: 007_metered_usage
Create Date: 2026-04-18 20:00:00.000000

Adds the durable state backing Phase 3's staged business launch workflow and
the scheduled-job watermarks that gate daily/weekly agent crons.

Tables:
  business_launches — one row per launch attempt, holds current_step + status
  launch_steps      — per-step journal with output payload and error text
  scheduled_jobs    — single-row-per-job-name table holding last_run_at
                      (idempotency guard for the in-process scheduler)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_launches_and_schedules"
down_revision: str | None = "007_metered_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_launches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("current_step", sa.String(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('pending','running','completed','failed','cancelled')",
            name="business_launches_status_check",
        ),
    )
    op.create_index(
        "ix_business_launches_business",
        "business_launches",
        ["business_id"],
    )
    # One active launch per business at a time. Partial unique index so
    # retries after failure can create a fresh row.
    op.create_index(
        "ix_business_launches_active",
        "business_launches",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("status in ('pending','running')"),
    )

    op.create_table(
        "launch_steps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "launch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_launches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "output",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('pending','running','completed','failed','skipped')",
            name="launch_steps_status_check",
        ),
        sa.UniqueConstraint("launch_id", "step_name", name="uq_launch_steps_launch_step"),
    )
    op.create_index(
        "ix_launch_steps_launch_order",
        "launch_steps",
        ["launch_id", "step_order"],
    )

    op.create_table(
        "scheduled_jobs",
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_jobs")
    op.drop_index("ix_launch_steps_launch_order", table_name="launch_steps")
    op.drop_table("launch_steps")
    op.drop_index("ix_business_launches_active", table_name="business_launches")
    op.drop_index("ix_business_launches_business", table_name="business_launches")
    op.drop_table("business_launches")

"""computer_use_escalations: queue of computer-use tasks the desktop runs

Revision ID: 008_computer_use_escalations
Revises: 007_metered_usage
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_computer_use_escalations"
down_revision: str | None = "007_metered_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "computer_use_escalations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
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
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("requester", sa.String(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("app_hint", sa.String(), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('queued','claimed','running','succeeded','failed','cancelled')",
            name="computer_use_escalations_status_check",
        ),
    )
    # Desktop poll path: "what's queued or running for this user, newest first?"
    op.create_index(
        "ix_cu_escalations_user_status_created",
        "computer_use_escalations",
        ["user_id", "status", sa.text("created_at DESC")],
    )
    # Per-business activity views.
    op.create_index(
        "ix_cu_escalations_business_created",
        "computer_use_escalations",
        ["business_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_cu_escalations_business_created", table_name="computer_use_escalations")
    op.drop_index("ix_cu_escalations_user_status_created", table_name="computer_use_escalations")
    op.drop_table("computer_use_escalations")

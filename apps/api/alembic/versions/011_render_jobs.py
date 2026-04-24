"""Creative Studio render jobs

Revision ID: 011_render_jobs
Revises: 010_account_integrations
Create Date: 2026-04-19 01:00:00.000000

Phase B: Muse renders images + video ads via user-provided provider keys.
One row per render. Status transitions: pending → queued → running →
completed | failed | cancelled.

Why both `business_id` and `user_id`:
  * `business_id` is nullable so test renders from the global Studio view
    (before picking a specific business) still land in the user's timeline.
  * `user_id` is always set and is the tenant boundary for queries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_render_jobs"
down_revision: str | None = "010_account_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "render_jobs",
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
            sa.ForeignKey("businesses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("external_job_id", sa.String(), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("cost_cents_estimate", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_cents_actual", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="render_jobs_status_check",
        ),
        sa.CheckConstraint(
            "mode in ('image','video')",
            name="render_jobs_mode_check",
        ),
    )
    op.create_index(
        "ix_render_jobs_user_created",
        "render_jobs",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_render_jobs_business_created",
        "render_jobs",
        ["business_id", sa.text("created_at DESC")],
    )
    # Quick lookup for the poller.
    op.create_index(
        "ix_render_jobs_active",
        "render_jobs",
        ["status"],
        postgresql_where=sa.text("status in ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_render_jobs_active", table_name="render_jobs")
    op.drop_index("ix_render_jobs_business_created", table_name="render_jobs")
    op.drop_index("ix_render_jobs_user_created", table_name="render_jobs")
    op.drop_table("render_jobs")

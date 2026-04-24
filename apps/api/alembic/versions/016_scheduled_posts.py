"""Scheduled posts table.

Revision ID: 016_scheduled_posts
Revises: 015_content_spine
Create Date: 2026-04-19 21:00:00.000000

Phase 9 of the Creative Studio revamp. One row per (creative, platform,
scheduled_at) publish request. The scheduler tick picks up due rows and
executes the push through the connected platform provider.

Lifecycle:
    scheduled        — waiting for scheduled_at
    publishing       — scheduler tick is mid-publish
    published        — live on the platform
    failed           — provider rejected; manual retry from UI
    cancelled        — user cancelled before publish

Cancel semantics: the user can cancel any row in state='scheduled' at
any time — there's no hard lockout window. The 24h "graceful cancel"
the PRD mentions is a UX nudge in the client, not a server-enforced
rule.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_scheduled_posts"
down_revision: str | None = "015_content_spine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_posts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "master_creative_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("master_creatives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("aspect", sa.String(), nullable=False),
        sa.Column(
            "scheduled_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column("caption", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("video_url", sa.Text()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("external_post_id", sa.String()),
        sa.Column("external_post_url", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
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
            "status in ('scheduled','publishing','published','failed','cancelled')",
            name="scheduled_posts_status_check",
        ),
    )
    op.create_index(
        "ix_scheduled_posts_due",
        "scheduled_posts",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_scheduled_posts_business_scheduled_at",
        "scheduled_posts",
        ["business_id", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_posts_business_scheduled_at", "scheduled_posts")
    op.drop_index("ix_scheduled_posts_due", "scheduled_posts")
    op.drop_table("scheduled_posts")

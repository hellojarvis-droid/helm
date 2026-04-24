"""Sync records — bidirectional-sync bookkeeping

Revision ID: 012_sync_records
Revises: 011_render_jobs
Create Date: 2026-04-19 02:00:00.000000

One row per (business, entity_type, external_id). Every push or pull
that flows through `services/sync_bus.py` bumps the timestamps + error
fields here, so the UI can render "Synced 2s ago · via webhook" status
chips without guessing.

Conflict semantics: **Helm wins** — `local_updated_at` is the moment a
Helm-side mutation was committed. When a webhook lands after that, the
pull handler compares `event_timestamp > local_updated_at` and only
applies the external change when the external event is strictly newer.

`entity_type` is a short slug the sync_bus register() keys off of, e.g.
`stripe_card_caps`, `shopify_product`, `connection_status`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_sync_records"
down_revision: str | None = "011_render_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_records",
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
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column(
            "last_direction",
            sa.String(),
            nullable=False,
            server_default=sa.text("'push'"),
        ),
        sa.Column(
            "last_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'ok'"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "local_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "external_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "last_direction in ('push','pull')",
            name="sync_records_direction_check",
        ),
        sa.CheckConstraint(
            "last_status in ('ok','failed','conflict')",
            name="sync_records_status_check",
        ),
        sa.UniqueConstraint(
            "entity_type",
            "external_id",
            name="uq_sync_records_entity_external",
        ),
    )
    op.create_index(
        "ix_sync_records_business",
        "sync_records",
        ["business_id", "entity_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_records_business", table_name="sync_records")
    op.drop_table("sync_records")

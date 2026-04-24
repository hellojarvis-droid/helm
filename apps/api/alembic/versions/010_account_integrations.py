"""Account-scoped (per-user) integrations table

Revision ID: 010_account_integrations
Revises: 009_integration_api_keys
Create Date: 2026-04-19 00:00:00.000000

Some integrations are per-business (Shopify store, Stripe Connect, Meta
Ads for a specific brand). Others belong to the user — one Runway account
fuels every Helm business they run.

Per-user rows live here; per-business rows stay on `integrations`. Both
share the same api-key-ciphertext + Composio-connection shape so the
vault helpers and UI patterns apply uniformly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_account_integrations"
down_revision: str | None = "009_integration_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_integrations",
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
        sa.Column("toolkit", sa.String(), nullable=False),
        sa.Column(
            "auth_mode",
            sa.String(),
            nullable=False,
            server_default=sa.text("'api_key'"),
        ),
        sa.Column("composio_connection_id", sa.String(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "metadata",
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
        sa.UniqueConstraint("user_id", "toolkit", name="uq_account_integrations_user_toolkit"),
    )


def downgrade() -> None:
    op.drop_table("account_integrations")

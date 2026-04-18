"""User subscription state — Stripe customer + subscription IDs

Revision ID: 006_subscription_state
Revises: 005_push_tokens
Create Date: 2026-04-18 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_subscription_state"
down_revision: str | None = "005_push_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'inactive'"),
        ),
    )
    op.add_column("users", sa.Column("stripe_price_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "stripe_price_id")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")

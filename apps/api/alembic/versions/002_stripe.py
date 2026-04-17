"""Stripe integration: onboarding + issuing state on businesses

Revision ID: 002_stripe
Revises: 001_initial
Create Date: 2026-04-17 19:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_stripe"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column(
            "stripe_onboarding_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "businesses",
        sa.Column("stripe_issuing_cardholder_id", sa.String(), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "stripe_meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("businesses", "stripe_meta")
    op.drop_column("businesses", "stripe_issuing_cardholder_id")
    op.drop_column("businesses", "stripe_onboarding_complete")

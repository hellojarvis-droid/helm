"""User metered subscription item + last-reported timestamp

Revision ID: 007_metered_usage
Revises: 006_subscription_state
Create Date: 2026-04-18 02:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_metered_usage"
down_revision: str | None = "006_subscription_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Stripe SubscriptionItem ID for the metered usage component (one per
    # subscription that includes a metered price). NULL when the user is on
    # a flat-only plan or before they upgrade.
    op.add_column(
        "users",
        sa.Column("stripe_metered_item_id", sa.String(), nullable=True),
    )
    # The last `created_at` timestamp on agent_events whose cost we've
    # reported to Stripe. We sum events strictly after this on each report
    # so usage isn't double-counted when reports overlap.
    op.add_column(
        "users",
        sa.Column("last_usage_reported_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_usage_reported_at")
    op.drop_column("users", "stripe_metered_item_id")

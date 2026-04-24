"""Expenses + tax export.

Revision ID: 017_expenses
Revises: 016_scheduled_posts
Create Date: 2026-04-19 22:00:00.000000

Phase 11 of the Creative Studio revamp. Helm tracks every dollar the
business spends so year-end tax prep is a CSV export, not a
reconstruction project. Expenses come from:

    * email    — Gmail receipt sync via Composio (scheduler tick reads
                 the connected inbox, parses receipts, writes rows)
    * manual   — the user pastes a receipt URL + amount
    * card     — pulled from the business's Stripe Issuing authorizations
                 (we already have those as `authorizations` — this is a
                 convenience mirror keyed to the expense taxonomy)

The `category` column uses a small, tax-prep-friendly taxonomy:
advertising, cogs, software, contractors, travel, meals, utilities,
supplies, legal, bank_fees, shipping, other.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_expenses"
down_revision: str | None = "016_scheduled_posts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expenses",
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
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'USD'"),
        ),
        sa.Column("vendor", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String()),
        sa.Column("description", sa.Text()),
        sa.Column("receipt_url", sa.Text()),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
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
            "source in ('email','manual','card')",
            name="expenses_source_check",
        ),
        sa.CheckConstraint(
            "category in ('advertising','cogs','software','contractors',"
            "'travel','meals','utilities','supplies','legal','bank_fees',"
            "'shipping','other')",
            name="expenses_category_check",
        ),
        sa.CheckConstraint("amount_cents >= 0", name="expenses_amount_nonneg"),
    )
    # Prevent duplicate rows from email sync re-pulling the same receipt.
    op.create_index(
        "uq_expenses_source_ref",
        "expenses",
        ["business_id", "source", "source_ref"],
        unique=True,
        postgresql_where=sa.text("source_ref IS NOT NULL"),
    )
    op.create_index(
        "ix_expenses_business_date",
        "expenses",
        ["business_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_expenses_business_date", "expenses")
    op.drop_index("uq_expenses_source_ref", "expenses")
    op.drop_table("expenses")

"""Credits system — balances + transactions

Revision ID: 014_credits_system
Revises: 013_storefronts_products
Create Date: 2026-04-19 18:00:00.000000

App-wide billing primitive (replaces bring-your-own-keys). Every
billable action — LLM turn, image/video render, VO, music gen, publish,
domain registration — decrements `credit_balances.balance_cents` and
leaves an audit row in `credit_transactions`.

Design choices fixed by user decision:

  * Denominated in **cents** (1 credit = 1¢). No floating-point, no
    exchange rates, no surprise conversions. Display formats as dollars.
  * Single balance column. Subscription grants, purchases, and refunds
    all flow into the same balance; rollover is automatic because we
    never "expire" unused credits within a cycle — we just don't
    double-grant. The monthly grant is idempotent per (user, cycle).
  * Markup ≈ 1% on downstream usage. Stripe processing fee on top-ups
    is shown transparently to the user ("$0.88 Stripe · not Helm") and
    charged on top so the user receives exactly what they paid for in
    credits. Captured here only as metadata on the purchase row; the
    debit for the fee itself stays in Stripe's world, not ours.
  * `reference_{type,id}` points back at the thing that caused the
    movement (render_job id, publish id, llm turn id, top-up session
    id, etc.) so a tax export / audit can reconstruct every penny.
  * **Reservation pattern.** Atomic hold: debit `estimate * 1.2` up
    front as kind='reserve'; on success book the actual debit and a
    partial refund for the unused headroom; on failure refund the
    whole reservation. Both reserve and its eventual
    commit/refund live as separate `credit_transactions` rows linked
    by `reservation_id` so the log tells the full story.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_credits_system"
down_revision: str | None = "013_storefronts_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One row per user. balance_cents is non-negative by constraint; every
    # mutation goes through services/credits.py which enforces atomicity.
    op.create_table(
        "credit_balances",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "balance_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # Running totals — useful for UI and tax reporting without
        # aggregating the transactions table on every load.
        sa.Column(
            "lifetime_granted_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "lifetime_purchased_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "lifetime_spent_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "balance_cents >= 0",
            name="credit_balances_nonneg",
        ),
    )

    op.create_table(
        "credit_transactions",
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
        # kind vocabulary:
        #   starter_grant       — $5 signup bonus
        #   subscription_grant  — monthly tier allowance
        #   purchase            — Stripe top-up settled
        #   reserve             — atomic hold before a billable action
        #   commit              — final debit of the actual cost after success
        #   refund              — reservation returned after failure/partial
        #   adjustment          — operator correction (customer support)
        sa.Column("kind", sa.String(), nullable=False),
        # Positive = credit to user (grants, purchases, refunds). Negative =
        # debit (reserves, commits). Sum of amount_cents over a user equals
        # their current balance — simple invariant, easy to audit.
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        # Snapshot of the balance AFTER this transaction, for fast history
        # rendering without running aggregates.
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        # Reservation chaining — `reserve` emits a row with a new
        # reservation_id; the eventual `commit` and any `refund` rows
        # reference it so the log shows the full lifecycle.
        sa.Column(
            "reservation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Points at the domain object the movement is about. reference_type
        # is a free-form slug (render_job | publish | llm_turn | top_up |
        # subscription_cycle | adjustment). reference_id is its UUID when
        # applicable.
        sa.Column("reference_type", sa.String(), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Stripe linkage on purchase rows.
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(), nullable=True),
        # Short human description for the history view.
        sa.Column("description", sa.Text(), nullable=False),
        # Structured meta — provider costs, markup breakdown, etc.
        sa.Column(
            "meta",
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
            "kind in ('starter_grant','subscription_grant','purchase',"
            "'reserve','commit','refund','adjustment')",
            name="credit_transactions_kind_check",
        ),
        sa.CheckConstraint(
            "balance_after_cents >= 0",
            name="credit_transactions_balance_nonneg",
        ),
    )
    op.create_index(
        "ix_credit_transactions_user_created",
        "credit_transactions",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_credit_transactions_reservation",
        "credit_transactions",
        ["reservation_id"],
        postgresql_where=sa.text("reservation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_credit_transactions_reference",
        "credit_transactions",
        ["reference_type", "reference_id"],
        postgresql_where=sa.text("reference_id IS NOT NULL"),
    )

    # Track the monthly subscription grant as idempotent (user, cycle)
    # so a webhook replay or clock drift doesn't double-credit.
    op.create_table(
        "subscription_grants",
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
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("cycle_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "credit_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id", "cycle_start", name="uq_subscription_grants_user_cycle"
        ),
    )


def downgrade() -> None:
    op.drop_table("subscription_grants")
    op.drop_index(
        "ix_credit_transactions_reference", table_name="credit_transactions"
    )
    op.drop_index(
        "ix_credit_transactions_reservation", table_name="credit_transactions"
    )
    op.drop_index(
        "ix_credit_transactions_user_created", table_name="credit_transactions"
    )
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")

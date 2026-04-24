"""Core database models.

Every business-scoped table carries `business_id`; every user-scoped table carries
`user_id`. The CLAUDE.md hard rule is: multi-tenant from line 1. Enforcement is
belt-and-braces — RLS policies on Supabase, plus tenant-scoped query helpers in
`helm.db.tenant`, plus integration tests that assert cross-tenant queries fail closed.

Schema is defined per `docs/ARCHITECTURE.md` §5. Changes require a new Alembic
migration — never edit an existing migration in place.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. Alembic autogenerate reads `Base.metadata`."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    supabase_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'founder'"))
    kill_switch_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    expo_push_token: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subscription_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'inactive'")
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_metered_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_usage_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "tier in ('founder','operator','portfolio')",
            name="users_tier_check",
        ),
    )


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    vertical: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'initializing'")
    )
    stripe_account_id: Mapped[str | None] = mapped_column(String)
    stripe_card_id: Mapped[str | None] = mapped_column(String)
    stripe_onboarding_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    stripe_issuing_cardholder_id: Mapped[str | None] = mapped_column(String)
    stripe_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    shopify_shop_domain: Mapped[str | None] = mapped_column(String)
    brand_kit: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    weekly_spend_cap_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("50000")
    )
    per_auth_cap_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("50000")
    )
    allowed_mcc_codes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('initializing','active','paused','archived')",
            name="businesses_status_check",
        ),
    )


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
    )
    managed_agent_session_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_agent_events_session_created", "session_id", "created_at"),
        Index("ix_agent_events_business_created", "business_id", "created_at"),
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','approved','modified','denied','expired')",
            name="approvals_status_check",
        ),
        CheckConstraint(
            "kind in ('spend','publish','delete','other')",
            name="approvals_kind_check",
        ),
    )


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class BusinessLaunch(Base):
    """One row per launch attempt for a business.

    Phase 3's durable state — the scheduler reads current_step on restart and
    picks up from the next pending step in `launch_steps`. Only one launch
    can be active (pending/running) per business at any time (enforced by
    partial unique index).
    """

    __tablename__ = "business_launches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    current_step: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','completed','failed','cancelled')",
            name="business_launches_status_check",
        ),
    )


class LaunchStep(Base):
    """One row per named step in a launch. Written eagerly on transition —
    the row existing means the step ran (or is running); the output/error
    fields are the result when status terminates."""

    __tablename__ = "launch_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    launch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_launches.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','completed','failed','skipped')",
            name="launch_steps_status_check",
        ),
        UniqueConstraint("launch_id", "step_name", name="uq_launch_steps_launch_step"),
        Index("ix_launch_steps_launch_order", "launch_id", "step_order"),
    )


class ScheduledJob(Base):
    """Idempotency watermark for the in-process scheduler.

    One row per named job. `last_run_at` is the scheduler's 'nothing to do if
    we've already run since X' guard — daily jobs refuse to run twice within
    24h, weekly within 7d, etc.
    """

    __tablename__ = "scheduled_jobs"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class RenderJob(Base):
    """Creative Studio render — one row per submitted generation.

    Status machine:
      pending → queued → running → completed | failed | cancelled
    """

    __tablename__ = "render_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="SET NULL"),
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    external_job_id: Mapped[str | None] = mapped_column(String)
    output_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    cost_cents_estimate: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_cents_actual: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="render_jobs_status_check",
        ),
        CheckConstraint(
            "mode in ('image','video')",
            name="render_jobs_mode_check",
        ),
    )


class AccountIntegration(Base):
    """Per-user, account-wide integrations.

    Account-level connectors (Creative providers like Runway/Higgsfield,
    personal tools like Gmail/Figma) attach to the user, not to a specific
    business. One row per (user_id, toolkit).

    Per-business integrations live on `integrations`; they share the same
    `auth_mode` + `api_key_ciphertext` + `composio_connection_id` shape.
    """

    __tablename__ = "account_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    toolkit: Mapped[str] = mapped_column(String, nullable=False)
    auth_mode: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'api_key'")
    )
    composio_connection_id: Mapped[str | None] = mapped_column(String)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "toolkit", name="uq_account_integrations_user_toolkit"),
    )


class HelmStorefront(Base):
    """Per-business first-party checkout page at `helm.app/s/<slug>`.

    For users without Shopify / TikTok Shop. The slug is globally unique;
    `published=false` keeps the public page from rendering. `theme`
    holds palette + hero copy overrides; the default paper palette is
    used when empty.
    """

    __tablename__ = "helm_storefronts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    tagline: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class Product(Base):
    """Per-business product SKU — source of truth for the Helm Storefront
    and the mirror target for Shopify/TikTok/Amazon via `external_refs`.

    Price is in cents (integer). `inventory_qty=NULL` means "unlimited"
    / "don't track"; 0 means out of stock.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    compare_at_price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(
        String(length=3), nullable=False, server_default=text("'usd'")
    )
    inventory_qty: Mapped[int | None] = mapped_column(Integer)
    images: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    external_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="products_price_check"),
        Index("ix_products_business_published", "business_id", "published"),
    )


class SyncRecord(Base):
    """Bidirectional-sync bookkeeping — one row per (entity_type, external_id).

    Every push (Helm → external) and pull (webhook → Helm) that flows
    through `services/sync_bus.py` updates this row. The UI reads it to
    render "Synced X ago · via webhook / via push" status chips.

    Conflict policy ("Helm wins"): `local_updated_at` is set on every
    committed Helm mutation. When an inbound event arrives with an
    earlier timestamp, the pull handler refuses to overwrite and writes
    `last_status='conflict'` instead so a diff banner can surface.
    """

    __tablename__ = "sync_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    last_direction: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'push'")
    )
    last_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'ok'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    local_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "last_direction in ('push','pull')",
            name="sync_records_direction_check",
        ),
        CheckConstraint(
            "last_status in ('ok','failed','conflict')",
            name="sync_records_status_check",
        ),
        UniqueConstraint(
            "entity_type", "external_id", name="uq_sync_records_entity_external"
        ),
    )


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    toolkit: Mapped[str] = mapped_column(String, nullable=False)
    # Present for Composio-backed integrations; NULL for api-key and
    # Helm-managed (env-key) integrations.
    composio_connection_id: Mapped[str | None] = mapped_column(String)
    # How the integration authenticates. 'composio' | 'api_key' | 'helm_managed'.
    auth_mode: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'composio'")
    )
    # Fernet ciphertext (ASCII base64). Decrypted via
    # services.integration_vault — never read raw.
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("business_id", "toolkit", name="uq_integrations_business_toolkit"),
    )


# ────────────────────────────────────────────────────────────────────
# Credits — app-wide billing primitive (cents-denominated).
# See alembic/014_credits_system.py for the full rationale.
# ────────────────────────────────────────────────────────────────────


class CreditBalance(Base):
    """One row per user. `services/credits.py` is the only module that
    mutates this; callers never UPDATE it directly."""

    __tablename__ = "credit_balances"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    lifetime_granted_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    lifetime_purchased_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    lifetime_spent_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("balance_cents >= 0", name="credit_balances_nonneg"),
    )


class CreditTransaction(Base):
    """Append-only ledger. Sum of `amount_cents` per user == balance_cents.

    Kinds:
      starter_grant — $5 signup bonus
      subscription_grant — tier's monthly allowance
      purchase — Stripe top-up settled
      reserve — pre-action hold (negative; linked to reservation_id)
      commit — final debit of actual cost (negative)
      refund — reservation return (positive)
      adjustment — operator correction
    """

    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reference_type: Mapped[str | None] = mapped_column(String)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "kind in ('starter_grant','subscription_grant','purchase',"
            "'reserve','commit','refund','adjustment')",
            name="credit_transactions_kind_check",
        ),
        CheckConstraint(
            "balance_after_cents >= 0",
            name="credit_transactions_balance_nonneg",
        ),
        Index(
            "ix_credit_transactions_user_created",
            "user_id",
            text("created_at DESC"),
        ),
    )


class SubscriptionGrant(Base):
    """Idempotency guard so we never double-grant a user's monthly tier
    allowance — a Stripe webhook replay or clock drift is caught by the
    (user_id, cycle_start) unique constraint."""

    __tablename__ = "subscription_grants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier: Mapped[str] = mapped_column(String, nullable=False)
    cycle_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cycle_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    credit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "cycle_start", name="uq_subscription_grants_user_cycle"
        ),
    )


# ────────────────────────────────────────────────────────────────────
# Creative Studio content spine — see alembic/015_content_spine.py.
# Populated by the DAG of specialists (Phase 3+). One Campaign →
# many Master Creatives → each has Shots + Format Renders.
# ────────────────────────────────────────────────────────────────────


class BrandLibrary(Base):
    """First-class brand kit per business. Replaces the legacy
    `businesses.brand_kit` JSON blob as the source of truth for
    everything written after migration 015. The old column stays for
    backwards-compat reads; new writes land here."""

    __tablename__ = "brand_libraries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    tagline: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String)
    palette: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    typography: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    logos: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    voice_paragraph: Mapped[str | None] = mapped_column(Text)
    banned_phrases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    winning_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    moodboard_urls: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class Campaign(Base):
    """Organizing unit. One Brief-head lives at a time; Master Creatives
    attached via `campaign_id` populate the Library view."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'drafting'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('drafting','rendering','ready','archived')",
            name="campaigns_status_check",
        ),
    )


class CreativeBrief(Base):
    """Append-only versioned Brief log. v1 is Creative Director's
    initial expansion; v2+ folds in Performance's Learnings Packet."""

    __tablename__ = "creative_briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_input: Mapped[str | None] = mapped_column(Text)
    angles: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    chosen_angle: Mapped[str | None] = mapped_column(Text)
    hook: Mapped[str | None] = mapped_column(Text)
    narrative_arc: Mapped[str | None] = mapped_column(Text)
    tone_descriptors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    forbidden_territory: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    task_packets: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    learnings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Integer))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "version", name="uq_creative_briefs_campaign_version"
        ),
    )


class MasterCreative(Base):
    """One finished ad. The unit the Library lists, scheduler schedules,
    Distributor publishes."""

    __tablename__ = "master_creatives"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    brief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creative_briefs.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    canonical_aspect: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'9:16'")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'drafting'")
    )
    copy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    timeline_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    canonical_output_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    imported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Integer))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('drafting','rendering','ready','failed','archived')",
            name="master_creatives_status_check",
        ),
    )


class Shot(Base):
    """Per master_creative video scene. Provider is Video Director's
    per-shot routing decision — don't replace with a campaign-level model."""

    __tablename__ = "shots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    master_creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_creatives.id", ondelete="CASCADE"),
        nullable=False,
    )
    shot_order: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )
    external_job_id: Mapped[str | None] = mapped_column(String)
    output_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("master_creative_id", "shot_order", name="uq_shots_master_order"),
        CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="shots_status_check",
        ),
    )


class FormatRender(Base):
    """Multi-format output per master + target surface. One-click reformat
    fans out into these; Editor fills `platform_copy` per-platform."""

    __tablename__ = "format_renders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    master_creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_creatives.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String, nullable=False)
    aspect: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )
    output_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    platform_copy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "master_creative_id",
            "platform",
            "aspect",
            name="uq_format_renders_master_platform_aspect",
        ),
        CheckConstraint(
            "mode in ('video','image','carousel')",
            name="format_renders_mode_check",
        ),
        CheckConstraint(
            "status in ('pending','rendering','ready','failed','skipped')",
            name="format_renders_status_check",
        ),
    )


class SafeZone(Base):
    """Per-platform pixel-percentage insets. Reference data refreshed
    quarterly. Editor + reformat read this to validate critical content
    stays inside the safe zone for the target platform."""

    __tablename__ = "safe_zones"

    platform: Mapped[str] = mapped_column(String, primary_key=True)
    aspect: Mapped[str] = mapped_column(String, primary_key=True)
    top_pct: Mapped[float] = mapped_column(nullable=False)
    bottom_pct: Mapped[float] = mapped_column(nullable=False)
    left_pct: Mapped[float] = mapped_column(nullable=False)
    right_pct: Mapped[float] = mapped_column(nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class FormatPreference(Base):
    """Pattern-learning watermark per business. After `times_seen >= 3`
    we auto-suggest the pattern on the reformat preview so the user
    doesn't have to pick the same 5 formats every campaign."""

    __tablename__ = "format_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    pattern_hash: Mapped[str] = mapped_column(String, nullable=False)
    pattern: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "business_id", "pattern_hash", name="uq_format_preferences_business_pattern"
        ),
    )


class ScheduledPost(Base):
    """One scheduled publish to a connected platform. The scheduler tick
    picks up rows where status='scheduled' AND scheduled_at <= now() and
    executes the push through the platform adapter."""

    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    master_creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_creatives.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String, nullable=False)
    aspect: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'scheduled'")
    )
    caption: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    video_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    external_post_id: Mapped[str | None] = mapped_column(String)
    external_post_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('scheduled','publishing','published','failed','cancelled')",
            name="scheduled_posts_status_check",
        ),
    )


class Expense(Base):
    """Business expense row. Tax-prep-friendly taxonomy; source tracks
    where the row came from (gmail sync, manual entry, or mirrored
    from a Stripe Issuing authorization)."""

    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    vendor: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    receipt_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "source in ('email','manual','card')",
            name="expenses_source_check",
        ),
        CheckConstraint(
            "category in ('advertising','cogs','software','contractors',"
            "'travel','meals','utilities','supplies','legal','bank_fees',"
            "'shipping','other')",
            name="expenses_category_check",
        ),
        CheckConstraint("amount_cents >= 0", name="expenses_amount_nonneg"),
    )


class Generation(Base):
    """Canvas-studio output. Unified row across Image / Video / Edit /
    Enhance / Lipsync — wraps one or more RenderJob rows. Session +
    parent give us 'use as reference' lineage and multi-tool flow."""

    __tablename__ = "generations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="SET NULL"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_generation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="SET NULL"),
    )
    tool: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )
    render_job_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    output_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    cost_cents_reserved: Mapped[int | None] = mapped_column(Integer)
    cost_cents_actual: Mapped[int | None] = mapped_column(Integer)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error: Mapped[str | None] = mapped_column(Text)
    favorited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "tool in ('image','video','edit','enhance','lipsync')",
            name="generations_tool_check",
        ),
        CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="generations_status_check",
        ),
    )


class Character(Base):
    """Trained identity reusable across generations (Soul-ID equivalent)."""

    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    reference_image_urls: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    trained_provider: Mapped[str | None] = mapped_column(String)
    trained_ref_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'untrained'")
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('untrained','training','ready','failed')",
            name="characters_status_check",
        ),
    )


class Style(Base):
    """Style reference / moodboard reusable across generations."""

    __tablename__ = "styles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    reference_image_urls: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    palette: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Preset(Base):
    """User-saved generation config (model + params + optional prompt)."""

    __tablename__ = "presets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    prompt_template: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "tool in ('image','video','edit','enhance','lipsync')",
            name="presets_tool_check",
        ),
    )


# ── Builder ──────────────────────────────────────────────────────────


class BuilderProject(Base):
    """A founder's Builder project. Points at a current version and the
    previous version (one-step undo target). `status='draft'` until the
    first build; `status='published'` after a successful publish."""

    __tablename__ = "builder_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="SET NULL"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'blank'")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    framework: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'vite'")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'draft'")
    )
    github_repo_url: Mapped[str | None] = mapped_column(Text)
    published_url: Mapped[str | None] = mapped_column(Text)
    custom_domain: Mapped[str | None] = mapped_column(Text)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    daily_spend_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    daily_spend_cap_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("500")
    )
    daily_spend_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "source_type in ('blank','import_github','import_zip')",
            name="builder_projects_source_check",
        ),
        CheckConstraint(
            "framework in ('next','vite','static','react_cra','other')",
            name="builder_projects_framework_check",
        ),
        CheckConstraint(
            "status in ('draft','ready','published','error')",
            name="builder_projects_status_check",
        ),
        UniqueConstraint("user_id", "slug", name="uq_builder_projects_user_slug"),
    )


class BuilderVersion(Base):
    """Snapshot of a project's file tree at a point in time. Every
    execute.apply writes a new row; undo restores the parent."""

    __tablename__ = "builder_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_versions.id", ondelete="SET NULL"),
    )
    label: Mapped[str | None] = mapped_column(String)
    change_summary_plain: Mapped[str | None] = mapped_column(Text)
    change_summary_technical: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String)
    snapshot_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class BuilderProjectFile(Base):
    """One file row per (version, path). Text content inline; binary
    assets (images, fonts) uploaded to Supabase Storage and referenced
    by `binary_url`."""

    __tablename__ = "builder_project_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    binary_url: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("version_id", "path", name="uq_builder_files_version_path"),
    )


class BuilderPlan(Base):
    """A proposed change. Moves through proposed → approved → applied,
    or proposed → rejected / failed."""

    __tablename__ = "builder_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    plain_plan: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    technical_plan: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    affected_areas: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    risks: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    file_hints: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    model_used: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'proposed'")
    )
    applied_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_versions.id", ondelete="SET NULL"),
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('proposed','approved','rejected','applied','failed')",
            name="builder_plans_status_check",
        ),
    )


class BuilderRun(Base):
    """Observability row per LLM call. Step ∈ {intent, plan, execute,
    verify, explain}."""

    __tablename__ = "builder_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("builder_plans.id", ondelete="SET NULL"),
    )
    step: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String)
    input_tokens: Mapped[int | None] = mapped_column(
        Integer, server_default=text("0")
    )
    output_tokens: Mapped[int | None] = mapped_column(
        Integer, server_default=text("0")
    )
    cost_cents: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'running'")
    )
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "step in ('intent','plan','execute','verify','explain')",
            name="builder_runs_step_check",
        ),
        CheckConstraint(
            "status in ('running','completed','failed')",
            name="builder_runs_status_check",
        ),
    )

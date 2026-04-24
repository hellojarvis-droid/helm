"""Canvas Creative Studio — unified generations + Library.

Revision ID: 018_canvas_studio
Revises: 017_expenses
Create Date: 2026-04-21 09:00:00.000000

The DAG-driven Creative Studio is retired. Canvas is per-tool
(Image / Video / Edit / Enhance / Lipsync) plus Library (Characters,
Styles, Presets) and a curator-only Marketing Studio.

Tables:

    generations    — unified output store. One row per user-visible
                     generation, wraps one or more render_jobs. Tracks
                     tool, model, prompt, references, params, status,
                     output, cost, session lineage, parent (for
                     "use as reference" chains).

    characters     — first-class trained identities (Soul-ID equivalent).

    styles         — moodboards / style references, reusable across
                     generations.

    presets        — user-saved generation configs (model + params +
                     optional prompt snippet) to one-click reapply.

Unchanged: render_jobs (execution unit), master_creatives / shots /
creative_briefs (Marketing-Studio curator tables), brand_libraries,
campaigns, format_renders, format_preferences, safe_zones.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018_canvas_studio"
down_revision: str | None = "017_expenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── generations ──────────────────────────────────────────────────
    op.create_table(
        "generations",
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
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parent_generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="SET NULL"),
        ),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "render_job_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("output_url", sa.Text()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("cost_cents_reserved", sa.Integer()),
        sa.Column("cost_cents_actual", sa.Integer()),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error", sa.Text()),
        sa.Column("favorited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            "tool in ('image','video','edit','enhance','lipsync')",
            name="generations_tool_check",
        ),
        sa.CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="generations_status_check",
        ),
    )
    op.create_index(
        "ix_generations_session",
        "generations",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_generations_user_created",
        "generations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_generations_business_tool",
        "generations",
        ["business_id", "tool", "created_at"],
    )

    # ── characters ───────────────────────────────────────────────────
    op.create_table(
        "characters",
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
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "reference_image_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("trained_provider", sa.String()),
        sa.Column("trained_ref_id", sa.String()),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'untrained'"),
        ),
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
            "status in ('untrained','training','ready','failed')",
            name="characters_status_check",
        ),
    )
    op.create_index("ix_characters_business", "characters", ["business_id"])

    # ── styles ───────────────────────────────────────────────────────
    op.create_table(
        "styles",
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
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "reference_image_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "palette",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_styles_business", "styles", ["business_id"])

    # ── presets ──────────────────────────────────────────────────────
    op.create_table(
        "presets",
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
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("prompt_template", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "tool in ('image','video','edit','enhance','lipsync')",
            name="presets_tool_check",
        ),
    )
    op.create_index("ix_presets_user_tool", "presets", ["user_id", "tool"])


def downgrade() -> None:
    op.drop_index("ix_presets_user_tool", "presets")
    op.drop_table("presets")
    op.drop_index("ix_styles_business", "styles")
    op.drop_table("styles")
    op.drop_index("ix_characters_business", "characters")
    op.drop_table("characters")
    op.drop_index("ix_generations_business_tool", "generations")
    op.drop_index("ix_generations_user_created", "generations")
    op.drop_index("ix_generations_session", "generations")
    op.drop_table("generations")

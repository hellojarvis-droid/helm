"""Creative Studio content spine

Revision ID: 015_content_spine
Revises: 014_credits_system
Create Date: 2026-04-19 19:00:00.000000

Phase 1 of the Creative Studio revamp. The full data model the DAG of
specialists writes into:

    brand_libraries      — per-business brand kit (first-class; replaces
                           the businesses.brand_kit JSON blob for
                           everything written after this migration)
    creative_briefs      — append-only versioned Brief log; each version
                           carries angles, hook, narrative arc, and the
                           task packets for each downstream specialist
    campaigns            — the organizing unit; one Brief-head at a time,
                           many master_creatives live under it
    master_creatives     — one per finished ad (unit the Library lists)
    shots                — per master_creative video scene, ordered, with
                           the model Video Director routed it to
    format_renders       — multi-format output row per (master, platform,
                           aspect); the one-click-reformat fan-out target
    safe_zones           — reference table of per-platform pixel insets
                           so Editor + reformat can validate against
                           current specs (refreshed quarterly)
    format_preferences   — per-business pattern-learning watermark: after
                           N=3 identical format choices we auto-suggest

The old `render_jobs` from the first Creative Studio keeps existing for
one more cycle — Phase 5's new /studio doesn't write to it. When the
rebuild lands, we'll archive the table in a later migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015_content_spine"
down_revision: str | None = "014_credits_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Brand Library ─────────────────────────────────────────────────
    # One row per business. URL-in onboarding (Phase 2) writes the
    # first row from a scraped website; the user then edits in the
    # Brand Library UI. `source_url` is what the scrape was based on
    # so we can re-scrape on request.
    op.create_table(
        "brand_libraries",
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
            unique=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        # Structured content: palette, typography, logo URLs, voice +
        # tone rules, banned phrases, winning references, moodboard.
        sa.Column(
            "palette",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "typography",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "logos",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("voice_paragraph", sa.Text(), nullable=True),
        sa.Column(
            "banned_phrases",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "winning_references",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "moodboard_urls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
            server_onupdate=sa.text("now()"),
        ),
    )

    # ── Campaigns ────────────────────────────────────────────────────
    op.create_table(
        "campaigns",
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
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'drafting'"),
        ),
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
            server_onupdate=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('drafting','rendering','ready','archived')",
            name="campaigns_status_check",
        ),
    )
    op.create_index(
        "ix_campaigns_business_created",
        "campaigns",
        ["business_id", sa.text("created_at DESC")],
    )

    # ── Creative Briefs (append-only versioned log) ──────────────────
    op.create_table(
        "creative_briefs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        # The raw user input that spawned this Brief. On v+1 it's the
        # previous learnings + any new user directive.
        sa.Column("user_input", sa.Text(), nullable=True),
        # Structured output of the Creative Director specialist.
        sa.Column(
            "angles",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chosen_angle", sa.Text(), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("narrative_arc", sa.Text(), nullable=True),
        sa.Column(
            "tone_descriptors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "forbidden_territory",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Per-specialist task packets. Each key is a specialist slug
        # ('copywriter', 'art_director', 'video_director', etc.) with
        # a {objective, deliverable_schema, effort_budget_tokens,
        # stop_conditions, forbidden_actions} dict as the value.
        sa.Column(
            "task_packets",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Performance feedback from the previous cycle (if any).
        sa.Column(
            "learnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Vector embedding of the Brief text — feeds library search.
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "campaign_id", "version", name="uq_creative_briefs_campaign_version"
        ),
    )
    op.create_index(
        "ix_creative_briefs_campaign",
        "creative_briefs",
        ["campaign_id", sa.text("version DESC")],
    )

    # ── Master Creatives (finished ads) ──────────────────────────────
    op.create_table(
        "master_creatives",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("creative_briefs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        # The canonical aspect the master was produced in. Reformat
        # outputs land as `format_renders` rows keyed off this id.
        sa.Column(
            "canonical_aspect",
            sa.String(),
            nullable=False,
            server_default=sa.text("'9:16'"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'drafting'"),
        ),
        # Headlines, captions (per-platform), CTA, hashtags, SSML hints
        # — Copywriter's structured output.
        sa.Column(
            "copy",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Editor's Timeline JSON a Remotion renderer can execute.
        sa.Column("timeline_json", postgresql.JSONB(), nullable=True),
        # Output URL of the canonical-aspect render (a convenience
        # pointer; the full multi-format set is in `format_renders`).
        sa.Column("canonical_output_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        # Set when the user uploads an external asset via "Import ad"
        # (Phase 10). Helm didn't generate this; we just orchestrate
        # reformat + schedule + publish.
        sa.Column(
            "imported",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Vector embedding of copy + key visual frames for library
        # search (Phase 7).
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
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
            server_onupdate=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('drafting','rendering','ready','failed','archived')",
            name="master_creatives_status_check",
        ),
    )
    op.create_index(
        "ix_master_creatives_campaign_created",
        "master_creatives",
        ["campaign_id", sa.text("created_at DESC")],
    )
    # Partial index for the Library's "Ready" filter — the most-hit query.
    op.create_index(
        "ix_master_creatives_ready",
        "master_creatives",
        ["campaign_id"],
        postgresql_where=sa.text("status = 'ready'"),
    )

    # ── Shots (per master_creative video scenes) ─────────────────────
    op.create_table(
        "shots",
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
        sa.Column("shot_order", sa.Integer(), nullable=False),
        # The model the Video Director routed this shot to (veo | kling
        # | runway | higgsfield | sora). Per-shot routing is the whole
        # point of the doc's architecture — don't replace with a
        # campaign-level model.
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("external_job_id", sa.String(), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "master_creative_id",
            "shot_order",
            name="uq_shots_master_order",
        ),
        sa.CheckConstraint(
            "status in ('pending','queued','running','completed','failed','cancelled')",
            name="shots_status_check",
        ),
    )

    # ── Format Renders (multi-format fan-out per master) ─────────────
    op.create_table(
        "format_renders",
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
        # Target surface: meta_reels / tiktok_in_feed / youtube_shorts /
        # instagram_feed_square / meta_stories / instagram_carousel /
        # etc. Stored as a free-form slug; validation + safe-zone
        # lookup in `safe_zones` reference table.
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("aspect", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),  # 'video' | 'image' | 'carousel'
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column(
            "platform_copy",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "master_creative_id",
            "platform",
            "aspect",
            name="uq_format_renders_master_platform_aspect",
        ),
        sa.CheckConstraint(
            "mode in ('video','image','carousel')",
            name="format_renders_mode_check",
        ),
        sa.CheckConstraint(
            "status in ('pending','rendering','ready','failed','skipped')",
            name="format_renders_status_check",
        ),
    )
    op.create_index(
        "ix_format_renders_master",
        "format_renders",
        ["master_creative_id"],
    )

    # ── Safe Zones reference data ────────────────────────────────────
    # Platform specs drift; refresh this table quarterly. Numbers are
    # percentage insets (0-100) off the full canvas so they scale to
    # any aspect. Editor + reformat check against these when
    # composing layers so critical content never hits the safe zone.
    op.create_table(
        "safe_zones",
        sa.Column("platform", sa.String(), primary_key=True),
        sa.Column("aspect", sa.String(), primary_key=True),
        sa.Column("top_pct", sa.Float(), nullable=False),
        sa.Column("bottom_pct", sa.Float(), nullable=False),
        sa.Column("left_pct", sa.Float(), nullable=False),
        sa.Column("right_pct", sa.Float(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
        ),
    )
    # Seed the current (Apr 2026) per-platform numbers from the
    # research doc. Refresh in a follow-up migration if platforms
    # publish new specs.
    op.bulk_insert(
        sa.table(
            "safe_zones",
            sa.column("platform", sa.String()),
            sa.column("aspect", sa.String()),
            sa.column("top_pct", sa.Float()),
            sa.column("bottom_pct", sa.Float()),
            sa.column("left_pct", sa.Float()),
            sa.column("right_pct", sa.Float()),
            sa.column("source_note", sa.String()),
        ),
        [
            # Meta Stories / Reels — the strictest baseline.
            {
                "platform": "meta_reels",
                "aspect": "9:16",
                "top_pct": 14.0,
                "bottom_pct": 35.0,
                "left_pct": 6.0,
                "right_pct": 6.0,
                "source_note": "Meta Stories/Reels safe zone, Apr 2026.",
            },
            {
                "platform": "meta_stories",
                "aspect": "9:16",
                "top_pct": 14.0,
                "bottom_pct": 35.0,
                "left_pct": 6.0,
                "right_pct": 6.0,
                "source_note": "Meta Stories/Reels safe zone, Apr 2026.",
            },
            # TikTok In-Feed — 1080x1920 canvas, approximate percentage conversion.
            {
                "platform": "tiktok_in_feed",
                "aspect": "9:16",
                "top_pct": 5.6,
                "bottom_pct": 16.7,
                "left_pct": 5.6,
                "right_pct": 11.1,
                "source_note": "TikTok In-Feed 108/320/60/120 on 1080x1920, Apr 2026.",
            },
            # YouTube Shorts — 180/390 on 1080x1920.
            {
                "platform": "youtube_shorts",
                "aspect": "9:16",
                "top_pct": 9.4,
                "bottom_pct": 20.3,
                "left_pct": 5.6,
                "right_pct": 5.6,
                "source_note": "YouTube Shorts insets on 1080x1920, Apr 2026.",
            },
            # Meta Feed 4:5.
            {
                "platform": "meta_feed",
                "aspect": "4:5",
                "top_pct": 8.0,
                "bottom_pct": 12.0,
                "left_pct": 5.0,
                "right_pct": 5.0,
                "source_note": "Meta Feed 4:5 safe zone estimate.",
            },
            # Instagram Feed square 1:1.
            {
                "platform": "instagram_feed",
                "aspect": "1:1",
                "top_pct": 6.0,
                "bottom_pct": 6.0,
                "left_pct": 6.0,
                "right_pct": 6.0,
                "source_note": "Instagram feed 1:1 safe zone estimate.",
            },
        ],
    )

    # ── Format Preferences (per-business pattern learning) ───────────
    op.create_table(
        "format_preferences",
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
        # A canonical hash of the ordered list of (platform, aspect)
        # tuples the user picked. After 3 identical hashes we auto-
        # suggest "use your standard N-format set?".
        sa.Column("pattern_hash", sa.String(), nullable=False),
        sa.Column(
            "pattern",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "times_seen",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "business_id", "pattern_hash", name="uq_format_preferences_business_pattern"
        ),
    )


def downgrade() -> None:
    op.drop_table("format_preferences")
    op.drop_table("safe_zones")
    op.drop_index("ix_format_renders_master", table_name="format_renders")
    op.drop_table("format_renders")
    op.drop_table("shots")
    op.drop_index("ix_master_creatives_ready", table_name="master_creatives")
    op.drop_index(
        "ix_master_creatives_campaign_created", table_name="master_creatives"
    )
    op.drop_table("master_creatives")
    op.drop_index("ix_creative_briefs_campaign", table_name="creative_briefs")
    op.drop_table("creative_briefs")
    op.drop_index("ix_campaigns_business_created", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_table("brand_libraries")

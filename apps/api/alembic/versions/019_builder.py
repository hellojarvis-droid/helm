"""Builder — projects, files, versions, plans, runs.

Revision ID: 019_builder
Revises: 018_canvas_studio
Create Date: 2026-04-21 13:00:00.000000

Data spine for Helm Builder. A founder's Builder project is a bag of
files with a pointer to `current_version_id` (what the preview renders)
and `previous_version_id` (one-step undo target).

    builder_projects       — one per founder-owned project
    builder_project_files  — current-version file contents (binary via storage)
    builder_versions       — snapshots; each execute.apply creates one
    builder_plans          — a proposed change, status-tracked
    builder_runs           — observability row per LLM call (step + cost)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019_builder"
down_revision: str | None = "018_canvas_studio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "builder_projects",
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
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "source_type",
            sa.String(),
            nullable=False,
            server_default=sa.text("'blank'"),
        ),
        sa.Column("source_url", sa.Text()),
        sa.Column(
            "framework",
            sa.String(),
            nullable=False,
            server_default=sa.text("'vite'"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("github_repo_url", sa.Text()),
        sa.Column("published_url", sa.Text()),
        sa.Column("custom_domain", sa.Text()),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("previous_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "daily_spend_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "daily_spend_cap_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("500"),
        ),
        sa.Column("daily_spend_reset_at", sa.DateTime(timezone=True)),
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
            "source_type in ('blank','import_github','import_zip')",
            name="builder_projects_source_check",
        ),
        sa.CheckConstraint(
            "framework in ('next','vite','static','react_cra','other')",
            name="builder_projects_framework_check",
        ),
        sa.CheckConstraint(
            "status in ('draft','ready','published','error')",
            name="builder_projects_status_check",
        ),
        sa.UniqueConstraint("user_id", "slug", name="uq_builder_projects_user_slug"),
    )
    op.create_index("ix_builder_projects_user", "builder_projects", ["user_id"])

    op.create_table(
        "builder_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("label", sa.String()),
        sa.Column("change_summary_plain", sa.Text()),
        sa.Column("change_summary_technical", sa.Text()),
        sa.Column("commit_sha", sa.String()),
        sa.Column(
            "snapshot_manifest",
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
    )
    op.create_index(
        "ix_builder_versions_project_created",
        "builder_versions",
        ["project_id", "created_at"],
    )

    op.create_table(
        "builder_project_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("binary_url", sa.Text()),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "version_id", "path", name="uq_builder_files_version_path"
        ),
    )
    op.create_index(
        "ix_builder_files_project", "builder_project_files", ["project_id"]
    )

    op.create_table(
        "builder_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("plain_plan", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "technical_plan", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "affected_areas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("risks", sa.Text()),
        sa.Column("recommendation", sa.Text()),
        sa.Column(
            "file_hints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("model_used", sa.String()),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column(
            "applied_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('proposed','approved','rejected','applied','failed')",
            name="builder_plans_status_check",
        ),
    )
    op.create_index(
        "ix_builder_plans_project_created",
        "builder_plans",
        ["project_id", "created_at"],
    )

    op.create_table(
        "builder_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builder_plans.id", ondelete="SET NULL"),
        ),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("model", sa.String()),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("cost_cents", sa.Integer(), server_default=sa.text("0")),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "step in ('intent','plan','execute','verify','explain')",
            name="builder_runs_step_check",
        ),
        sa.CheckConstraint(
            "status in ('running','completed','failed')",
            name="builder_runs_status_check",
        ),
    )
    op.create_index(
        "ix_builder_runs_project", "builder_runs", ["project_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_builder_runs_project", "builder_runs")
    op.drop_table("builder_runs")
    op.drop_index("ix_builder_plans_project_created", "builder_plans")
    op.drop_table("builder_plans")
    op.drop_index("ix_builder_files_project", "builder_project_files")
    op.drop_table("builder_project_files")
    op.drop_index("ix_builder_versions_project_created", "builder_versions")
    op.drop_table("builder_versions")
    op.drop_index("ix_builder_projects_user", "builder_projects")
    op.drop_table("builder_projects")

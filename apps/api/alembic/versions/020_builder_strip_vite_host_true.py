"""Strip `server: { host: true, ... }` from existing builder vite.config.js rows.

Pre-existing builder projects were seeded from a Vite template that
included `server: { host: true, port: 5173 }`. WebContainer can't proxy
a 0.0.0.0 bind, so the dev server's `server-ready` event never fires
and the in-browser preview hangs until the 60s timeout. The template
itself was fixed in services/builder/templates.py, but rows already in
the DB still have the bad config. This migration cleans them.

Idempotent: re-running matches nothing.
"""

from __future__ import annotations

from alembic import op


revision: str = "020_builder_strip_vite_host_true"
down_revision: str | None = "019_builder"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


# POSIX character classes — Postgres regexes don't have to grok `\s`.
# Matches an optional leading comma, the `server: { host: true, ... }`
# block, and trailing comma + newline so removal leaves clean syntax.
_PATTERN = (
    r"[[:space:]]*,?[[:space:]]*server:[[:space:]]*"
    r"\{[[:space:]]*host:[[:space:]]*true[^}]*\}"
    r"[[:space:]]*,?[[:space:]]*\n?"
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE builder_project_files
        SET content = regexp_replace(content, '{_PATTERN}', '', 'g')
        WHERE path = 'vite.config.js'
          AND content ~ 'host:[[:space:]]*true'
        """
    )


def downgrade() -> None:
    # Intentional no-op — re-introducing host:true would re-break the
    # WebContainer preview. If you truly need to revert, restore from
    # backup or hand-edit the affected rows.
    pass

"""Integration api_key ciphertext column

Revision ID: 009_integration_api_keys
Revises: 008_launches_and_schedules
Create Date: 2026-04-18 22:00:00.000000

Phase A: provider-key paste flow. Many AI-render providers (Runway,
Higgsfield, Kling, Nano-Banana) don't have OAuth; users (or Helm itself)
paste an API key. We store it encrypted with Fernet and decrypt on read.

`composio_connection_id` becomes nullable because api-key integrations
have no Composio connection backing them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_integration_api_keys"
down_revision: str | None = "008_launches_and_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # composio_connection_id is no longer required — api-key integrations set it
    # to NULL. Composio integrations still populate it.
    op.alter_column(
        "integrations",
        "composio_connection_id",
        existing_type=sa.String(),
        nullable=True,
    )
    # Ciphertext payload. Fernet tokens are base64 ASCII and fit in a TEXT
    # column. Never raw keys — wire the helpers in services/integration_vault.py.
    op.add_column(
        "integrations",
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
    )
    # Auth mode lets the UI render a matching badge without parsing ciphertext —
    # composio | api_key | helm_managed.
    op.add_column(
        "integrations",
        sa.Column("auth_mode", sa.String(), nullable=False, server_default=sa.text("'composio'")),
    )


def downgrade() -> None:
    op.drop_column("integrations", "auth_mode")
    op.drop_column("integrations", "api_key_ciphertext")
    op.alter_column(
        "integrations",
        "composio_connection_id",
        existing_type=sa.String(),
        nullable=False,
    )

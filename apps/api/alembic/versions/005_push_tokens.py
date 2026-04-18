"""User push notification tokens

Revision ID: 005_push_tokens
Revises: 004_mcc_allowlist
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_push_tokens"
down_revision: str | None = "004_mcc_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable — users who haven't registered a device yet stay NULL.
    # ExpoPushToken shapes look like "ExponentPushToken[...]" or
    # "ExpoPushToken[...]"; we store the raw string and let the Expo
    # Push API validate at send-time.
    op.add_column("users", sa.Column("expo_push_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "expo_push_token")

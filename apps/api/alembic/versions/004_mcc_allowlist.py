"""Per-business MCC allowlist override

Revision ID: 004_mcc_allowlist
Revises: 003_per_auth_cap
Create Date: 2026-04-17 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_mcc_allowlist"
down_revision: str | None = "003_per_auth_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable — NULL means "use default allowlist from stripe_authorization".
    op.add_column(
        "businesses",
        sa.Column("allowed_mcc_codes", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("businesses", "allowed_mcc_codes")

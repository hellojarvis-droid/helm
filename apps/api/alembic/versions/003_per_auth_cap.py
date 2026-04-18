"""Per-authorization spending cap on businesses

Revision ID: 003_per_auth_cap
Revises: 002_stripe
Create Date: 2026-04-17 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_per_auth_cap"
down_revision: str | None = "002_stripe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column(
            "per_auth_cap_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("50000"),
        ),
    )


def downgrade() -> None:
    op.drop_column("businesses", "per_auth_cap_cents")

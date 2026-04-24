"""Account-level connections — per-user integrations that fuel every
business (Runway, Higgsfield, Kling, Gmail, etc.).

Complements `routes/integrations.py` which handles per-business
connections (Shopify store, Meta ad account, etc.). Both share the same
auth_mode / api_key_ciphertext / composio_connection_id shape via the
matching db models + vault helpers.

Surfaces:

    GET  /connectors/catalog            — full connector list (static)
    GET  /connections/account           — user's current rows
    POST /connections/account/api_key/{slug}
                                        — paste + encrypt an API key
    POST /connections/account/oauth/{slug}
                                        — start Composio OAuth flow
    POST /connections/account/{slug}/sync
                                        — refresh upstream status (Composio)
    DELETE /connections/account/{slug}  — disconnect
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AccountIntegration
from helm.db.session import get_session
from helm.errors import upstream_unavailable
from helm.services import composio_client, integration_vault, provider_catalog
from helm.services.integration_vault import (
    IntegrationSecretMissingError,
)
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["connections"])


# ──────────────────────────────────────────────────────────
# Catalog
# ──────────────────────────────────────────────────────────


class ConnectorInfo(BaseModel):
    slug: str
    name: str
    category: str
    scope: str
    auth_mode: str
    description: str
    signup_url: str | None
    connect_hint: str
    popularity: int
    cost_hint: str


@router.get("/connectors/catalog", response_model=list[ConnectorInfo])
async def catalog() -> list[ConnectorInfo]:
    """Full connector list — feeds the Connections + per-business
    Integrations grids. Static, cacheable."""
    return [ConnectorInfo(**c.to_dict()) for c in provider_catalog.all_connectors()]


# ──────────────────────────────────────────────────────────
# Account-level connections
# ──────────────────────────────────────────────────────────


class ConnectionStatus(BaseModel):
    id: uuid.UUID
    toolkit: str
    auth_mode: str
    status: str
    has_api_key: bool
    masked_key: str | None
    composio_connection_id: str | None
    created_at: datetime
    metadata: dict[str, Any]


def _to_status(row: AccountIntegration) -> ConnectionStatus:
    plain = integration_vault.decrypt_key(row.api_key_ciphertext)
    return ConnectionStatus(
        id=row.id,
        toolkit=row.toolkit,
        auth_mode=row.auth_mode,
        status=row.status,
        has_api_key=row.api_key_ciphertext is not None,
        masked_key=integration_vault.mask_key(plain) if plain else None,
        composio_connection_id=row.composio_connection_id,
        created_at=row.created_at,
        metadata=row.meta,
    )


@router.get("/connections/account", response_model=list[ConnectionStatus])
async def list_account_connections(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ConnectionStatus]:
    user_row = await sync_user_from_supabase(db, user)
    rows = (
        (
            await db.execute(
                select(AccountIntegration)
                .where(AccountIntegration.user_id == user_row.id)
                .order_by(AccountIntegration.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_status(r) for r in rows]


class SaveApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=4, max_length=1000)


@router.post("/connections/account/api_key/{slug}", response_model=ConnectionStatus)
async def save_api_key(
    slug: str,
    body: SaveApiKeyRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ConnectionStatus:
    """Paste + encrypt an API key for an account-level connector.

    Only connectors with `auth_mode == 'api_key'` accept this. Composio-
    OAuth connectors redirect to `/connections/account/oauth/{slug}`.
    """
    connector = provider_catalog.get(slug)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"unknown connector '{slug}'")
    if connector.scope != "account":
        raise HTTPException(
            status_code=400,
            detail=(
                f"connector '{slug}' is business-scoped — use the per-business "
                "integrations endpoint instead"
            ),
        )
    if connector.auth_mode != "api_key":
        raise HTTPException(
            status_code=400,
            detail=f"connector '{slug}' uses Composio OAuth; call /oauth/{slug}",
        )

    try:
        ciphertext = integration_vault.encrypt_key(body.api_key.strip())
    except IntegrationSecretMissingError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "HELM_INTEGRATION_SECRET is not set on the API — cannot store "
                "user-provided keys until the operator adds it."
            ),
        ) from e

    user_row = await sync_user_from_supabase(db, user)
    existing_q = await db.execute(
        select(AccountIntegration).where(
            AccountIntegration.user_id == user_row.id,
            AccountIntegration.toolkit == connector.slug,
        )
    )
    existing = existing_q.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.auth_mode = "api_key"
        existing.api_key_ciphertext = ciphertext
        existing.status = "active"
        existing.meta = {**existing.meta, "connected_at": now.isoformat()}
        row = existing
    else:
        row = AccountIntegration(
            user_id=user_row.id,
            toolkit=connector.slug,
            auth_mode="api_key",
            api_key_ciphertext=ciphertext,
            status="active",
            meta={"connected_at": now.isoformat()},
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_status(row)


class OauthStartResponse(BaseModel):
    connection_id: uuid.UUID
    toolkit: str
    redirect_url: str
    status: str


@router.post("/connections/account/oauth/{slug}", response_model=OauthStartResponse)
async def start_oauth(
    slug: str,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> OauthStartResponse:
    """Kick off a Composio OAuth flow for an account-level connector.

    Returns the redirect URL the client opens in a new tab. Composio
    posts the status transitions back to `/webhooks/composio`, which
    flips the row to `active`.
    """
    connector = provider_catalog.get(slug)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"unknown connector '{slug}'")
    if connector.scope != "account":
        raise HTTPException(
            status_code=400,
            detail=f"connector '{slug}' is business-scoped",
        )
    if connector.auth_mode != "composio_oauth":
        raise HTTPException(
            status_code=400,
            detail=f"connector '{slug}' uses api-key paste; call /api_key/{slug}",
        )

    user_row = await sync_user_from_supabase(db, user)

    try:
        conn = await composio_client.initiate_connection(
            toolkit=connector.slug,
            user_id=user_row.id,
            business_id=None,
        )
    except RuntimeError as e:
        raise upstream_unavailable("The connection service") from e

    existing_q = await db.execute(
        select(AccountIntegration).where(
            AccountIntegration.user_id == user_row.id,
            AccountIntegration.toolkit == connector.slug,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        existing.auth_mode = "composio_oauth"
        existing.composio_connection_id = conn.connection_id
        existing.status = "pending"
        existing.meta = {"initiated_at": datetime.now(UTC).isoformat()}
        row = existing
    else:
        row = AccountIntegration(
            user_id=user_row.id,
            toolkit=connector.slug,
            auth_mode="composio_oauth",
            composio_connection_id=conn.connection_id,
            status="pending",
            meta={"initiated_at": datetime.now(UTC).isoformat()},
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)

    return OauthStartResponse(
        connection_id=row.id,
        toolkit=connector.slug,
        redirect_url=conn.redirect_url,
        status=row.status,
    )


@router.post("/connections/account/{slug}/sync", response_model=ConnectionStatus)
async def sync_account(
    slug: str,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ConnectionStatus:
    """Refresh an account connector's status from Composio (OAuth only)."""
    user_row = await sync_user_from_supabase(db, user)
    row_q = await db.execute(
        select(AccountIntegration).where(
            AccountIntegration.user_id == user_row.id,
            AccountIntegration.toolkit == slug,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if row.auth_mode != "composio_oauth" or not row.composio_connection_id:
        return _to_status(row)

    upstream = await composio_client.get_connection(row.composio_connection_id)
    upstream_status = str(upstream.get("status", "")).upper()
    if upstream_status == "ACTIVE":
        row.status = "active"
    elif upstream_status in {"FAILED", "INACTIVE"}:
        row.status = "failed"
    elif upstream_status == "EXPIRED":
        row.status = "expired"
    else:
        row.status = "pending"
    row.meta = {
        **row.meta,
        "last_sync": datetime.now(UTC).isoformat(),
        "upstream_status": upstream_status,
    }
    await db.commit()
    await db.refresh(row)
    return _to_status(row)


@router.delete("/connections/account/{slug}", status_code=204)
async def disconnect(
    slug: str,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Remove an account-level connection.

    For api-key connectors, we wipe the ciphertext (no external revoke —
    the user must rotate the key on the provider side if needed). For
    Composio connectors, we also ask Composio to deactivate. Best-effort
    on the Composio side; row removal always succeeds.
    """
    user_row = await sync_user_from_supabase(db, user)
    row_q = await db.execute(
        select(AccountIntegration).where(
            AccountIntegration.user_id == user_row.id,
            AccountIntegration.toolkit == slug,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="connection not found")

    # TODO: when Composio supports it, delete the managed connection via API.
    # For now, dropping our row is sufficient — the user can fully revoke at
    # the provider side too.
    await db.delete(row)
    await db.commit()

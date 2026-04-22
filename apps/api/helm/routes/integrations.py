"""Integrations routes — start an OAuth flow, check status, list.

Flow (polling-based for Session 4):
  1. Client POSTs /integrations/{business_id}/connect/{toolkit}.
     We call Composio's `toolkits.authorize`, get back a redirect URL +
     connection_id, insert a `pending` row into integrations, return both
     to the client.
  2. Client opens the redirect URL; user completes OAuth at the provider.
  3. Client polls /integrations/{integration_id}/sync. We call Composio
     `connected_accounts.get` and flip our row to `active` when the upstream
     status is ACTIVE.

Webhook-driven updates (Composio POSTs to us) land in Session 5 alongside
signature verification.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import Integration
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import upstream_unavailable
from helm.services import composio_client
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    toolkit: str
    composio_connection_id: str
    status: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: Integration) -> IntegrationResponse:
        return cls(
            id=row.id,
            business_id=row.business_id,
            toolkit=row.toolkit,
            composio_connection_id=row.composio_connection_id,
            status=row.status,
            metadata=row.meta,
            created_at=row.created_at,
        )


class ConnectResponse(BaseModel):
    integration_id: uuid.UUID
    toolkit: str
    redirect_url: str
    composio_connection_id: str
    status: str


@router.post("/{business_id}/connect/{toolkit}", response_model=ConnectResponse)
async def connect(
    business_id: uuid.UUID,
    toolkit: str,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ConnectResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    toolkit_slug = toolkit.lower().strip()
    if not toolkit_slug:
        raise HTTPException(status_code=422, detail="toolkit is required")

    # If a prior integration for this (business, toolkit) exists in pending/active,
    # reuse it — Composio supports one connection per (user_id, toolkit) by default.
    existing_q = await db.execute(
        select(Integration).where(
            Integration.business_id == business_id,
            Integration.toolkit == toolkit_slug,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing and existing.status == "active":
        raise HTTPException(
            status_code=409,
            detail="toolkit already connected for this business",
        )

    try:
        conn = await composio_client.initiate_connection(
            toolkit=toolkit_slug,
            user_id=user_row.id,
            business_id=business_id,
        )
    except RuntimeError as e:
        # Composio misconfigured or toolkit not enabled — log full detail,
        # return a canned message so we don't leak internal state to clients.
        raise upstream_unavailable("The integrations service") from e

    if existing is not None:
        existing.composio_connection_id = conn.connection_id
        existing.status = "pending"
        existing.meta = {"initiated_at": datetime.now(UTC).isoformat()}
        row = existing
    else:
        row = Integration(
            business_id=business_id,
            toolkit=toolkit_slug,
            composio_connection_id=conn.connection_id,
            status="pending",
            meta={"initiated_at": datetime.now(UTC).isoformat()},
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)

    return ConnectResponse(
        integration_id=row.id,
        toolkit=toolkit_slug,
        redirect_url=conn.redirect_url,
        composio_connection_id=conn.connection_id,
        status=row.status,
    )


@router.get("/{business_id}", response_model=list[IntegrationResponse])
async def list_integrations(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[IntegrationResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    rows = (
        (
            await db.execute(
                select(Integration)
                .where(Integration.business_id == business_id)
                .order_by(Integration.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [IntegrationResponse.from_row(r) for r in rows]


@router.post("/{integration_id}/sync", response_model=IntegrationResponse)
async def sync_integration(
    integration_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> IntegrationResponse:
    """Refresh an integration's status from Composio. Flips to 'active' when
    the upstream connection completes OAuth; flips to 'failed' / 'expired'
    on terminal upstream states.
    """
    user_row = await sync_user_from_supabase(db, user)
    res = await db.execute(select(Integration).where(Integration.id == integration_id))
    row = res.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="integration not found")

    biz = await get_business_for_user(db, user_row.id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="integration not found")

    upstream = await composio_client.get_connection(row.composio_connection_id)
    upstream_status = str(upstream.get("status", "")).upper()

    # Composio status → our status.
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
    return IntegrationResponse.from_row(row)

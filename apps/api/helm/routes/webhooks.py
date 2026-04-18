"""Webhooks — incoming events from external services.

Composio: POSTs connection lifecycle events (created / expired / inactive).
We verify the HMAC-SHA256 signature in the `X-Composio-Signature-256` header
against `COMPOSIO_WEBHOOK_SECRET`, then flip the matching `integrations` row
to the new status.

Sig format assumption: `sha256=<hex>` over the raw request body. If the
dashboard surfaces a different scheme when the user wires webhooks, we
adjust here. Constant-time compare via `hmac.compare_digest`.

Unknown event types return 200 after logging — we never want Composio
retrying forever because of a shape change we haven't caught up with.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import Business, Integration, User
from helm.db.session import get_session
from helm.services import event_log, stripe_authorization, stripe_billing, stripe_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger("helm.webhooks")

_SIG_HEADER = "x-composio-signature-256"
_SIG_PREFIX = "sha256="


def _verify_composio_signature(body: bytes, signature_header: str | None) -> bool:
    """HMAC-SHA256 verification against COMPOSIO_WEBHOOK_SECRET.

    Returns False if no secret is configured (fail-closed) so we never
    accept unsigned events by accident. In dev you can set the secret to a
    known value and replay real Composio requests; in prod it comes from
    the Render env.
    """
    settings = get_settings()
    secret = settings.composio_webhook_secret
    if not secret or signature_header is None:
        return False
    if not signature_header.startswith(_SIG_PREFIX):
        return False
    expected_hex = signature_header[len(_SIG_PREFIX) :]
    computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_hex)


def _status_from_event(event_type: str, payload: dict[str, Any]) -> str | None:
    """Return the integrations.status to set, or None to leave it alone."""
    # Composio event types follow `composio.<resource>.<action>`.
    if event_type.endswith(".expired"):
        return "expired"
    if event_type.endswith(".inactive") or event_type.endswith(".failed"):
        return "failed"
    # Connected/created/updated → look at the embedded status if present.
    data = payload.get("data") or payload.get("connected_account") or {}
    upstream_status = str(data.get("status", "")).upper()
    if upstream_status == "ACTIVE":
        return "active"
    if upstream_status == "FAILED":
        return "failed"
    if upstream_status == "EXPIRED":
        return "expired"
    return None


@router.post("/composio", status_code=status.HTTP_200_OK)
async def composio_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get(_SIG_HEADER)
    if not _verify_composio_signature(body, signature):
        log.warning(
            "webhook.bad_signature", has_secret=bool(get_settings().composio_webhook_secret)
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as e:
        log.warning("webhook.bad_json", err=str(e))
        raise HTTPException(status_code=400, detail="invalid json") from e

    event_type = str(payload.get("type") or payload.get("event_type") or "unknown")
    connection_id = _extract_connection_id(payload)
    log.info("webhook.received", event_type=event_type, connection_id=connection_id)

    if connection_id is None:
        return {"status": "ignored", "reason": "no connection_id in payload"}

    new_status = _status_from_event(event_type, payload)
    if new_status is None:
        return {"status": "ignored", "reason": "no status mapping for event"}

    # Flip the matching integrations row. Idempotent: re-delivery hits the same row.
    res = await db.execute(
        select(Integration).where(Integration.composio_connection_id == connection_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        # Not our connection — could be another tenant on the same Composio
        # workspace. 200 OK so Composio doesn't retry.
        return {"status": "ignored", "reason": "unknown connection_id"}

    row.status = new_status
    row.meta = {
        **row.meta,
        "last_webhook_event": event_type,
        "last_webhook_status": new_status,
    }
    await db.commit()
    return {"status": "ok", "integration_status": new_status}


def _extract_connection_id(payload: dict[str, Any]) -> str | None:
    """Composio webhooks carry the connection id under varying keys depending
    on event type. Check a few plausible locations before giving up."""
    for key in ("connection_id", "connected_account_id", "nanoid", "id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    data = payload.get("data") or payload.get("connected_account") or {}
    if isinstance(data, dict):
        for key in ("id", "connection_id", "nanoid"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


# ────────────────────────────────────────────────────────────────────
# Stripe webhook — Connect onboarding + Issuing authorizations + revenue
# ────────────────────────────────────────────────────────────────────


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe_client.verify_webhook(body, sig_header)
    except stripe.SignatureVerificationError as e:
        log.warning("stripe.bad_signature", err=str(e))
        raise HTTPException(status_code=401, detail="invalid signature") from e
    except RuntimeError as e:
        # Service-level config missing (secret unset). 503 so Stripe retries,
        # and the error surfaces as an ops issue rather than a 500.
        log.error("stripe.webhook_unconfigured", err=str(e))
        raise HTTPException(status_code=503, detail="webhook not configured") from e
    except ValueError as e:
        log.warning("stripe.bad_payload", err=str(e))
        raise HTTPException(status_code=400, detail="invalid payload") from e

    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    data_obj = (
        event.get("data", {}).get("object", {})
        if isinstance(event, dict)
        else event["data"]["object"]
    )
    log.info("stripe.event", type=event_type)

    if event_type == "account.updated":
        return await _handle_account_updated(db, data_obj)
    if event_type == "issuing_authorization.request":
        return await _handle_authorization_request(db, data_obj)
    if event_type == "payment_intent.succeeded":
        return await _handle_payment_succeeded(db, data_obj)
    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return await _handle_subscription_event(db, event_type, data_obj)

    # Unknown event type — ack so Stripe doesn't retry forever.
    return {"status": "ignored", "type": event_type}


async def _handle_account_updated(db: AsyncSession, account: dict[str, Any]) -> dict[str, Any]:
    account_id = str(account.get("id") or "")
    if not account_id:
        return {"status": "ignored", "reason": "no account id"}

    res = await db.execute(select(Business).where(Business.stripe_account_id == account_id))
    biz = res.scalar_one_or_none()
    if biz is None:
        return {"status": "ignored", "reason": "no business for account"}

    complete = stripe_client.account_onboarding_complete(account)
    if biz.stripe_onboarding_complete != complete:
        biz.stripe_onboarding_complete = complete
        biz.stripe_meta = {
            **biz.stripe_meta,
            "last_account_update": {
                "details_submitted": account.get("details_submitted"),
                "charges_enabled": account.get("charges_enabled"),
                "payouts_enabled": account.get("payouts_enabled"),
            },
        }
        await db.commit()

    return {"status": "ok", "onboarding_complete": complete}


async def _handle_authorization_request(
    db: AsyncSession, auth_obj: dict[str, Any]
) -> dict[str, Any]:
    """Synchronously decide a Stripe Issuing authorization AND enforce it.

    Stripe expects a response within 2 seconds. Our decision tree is all
    in-process Postgres reads; latency is bounded by one SELECT on
    `businesses` + one aggregate SELECT on `agent_events`.

    The webhook HTTP response body is advisory. The BINDING decision is the
    follow-up server-to-server `Issuing.Authorization.approve/decline` call
    we issue immediately after. If that enforcement fails we still return 200
    with the decision in the body — a 5xx storm-retry is worse than a stale
    decision (Stripe's own fallback `default` on the card still applies).
    """
    merchant = auth_obj.get("merchant_data") or {}
    amount_cents = int(auth_obj.get("pending_request", {}).get("amount", 0) or 0)
    category = merchant.get("category")
    name = merchant.get("name")
    account_id = str(auth_obj.get("stripe_account") or auth_obj.get("account") or "")
    authorization_id = str(auth_obj.get("id") or "")

    decision = await stripe_authorization.decide_authorization(
        db,
        stripe_account_id=account_id,
        amount_cents=amount_cents,
        merchant_category=category,
        merchant_name=name,
    )

    enforcement_error: str | None = None
    if authorization_id and account_id:
        try:
            if decision.approved:
                await stripe_client.approve_authorization(authorization_id, account_id)
            else:
                await stripe_client.decline_authorization(
                    authorization_id, account_id, reason=decision.reason
                )
        except Exception as e:
            log.error(
                "stripe.authorization_enforcement_failed",
                auth_id=authorization_id,
                err=str(e)[:300],
                approved=decision.approved,
            )
            enforcement_error = str(e)[:200]

    body: dict[str, Any] = {
        "approved": decision.approved,
        "reason": decision.reason,
        "amount_cents": decision.amount_cents,
    }
    if enforcement_error:
        body["enforcement_error"] = enforcement_error
    return body


async def _handle_subscription_event(
    db: AsyncSession, event_type: str, subscription: dict[str, Any]
) -> dict[str, Any]:
    """Keep users.tier + subscription state in sync with Stripe.

    - created / updated with an active-ish status → user.tier = tier_for_price
      and subscription_status = the Stripe status.
    - deleted → tier resets to 'founder' (the most restrictive default)
      and status = 'canceled'.
    """
    customer_id = stripe_billing.extract_customer_id(subscription)
    if not customer_id:
        return {"status": "ignored", "reason": "no customer id"}

    res = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    user = res.scalar_one_or_none()
    if user is None:
        # Could be a race where the checkout session created a customer on
        # Stripe but our /billing/checkout row hadn't committed yet. Stripe
        # retries, so acking is fine.
        return {"status": "ignored", "reason": "no user for customer"}

    status = str(subscription.get("status") or "").lower()
    sub_id = subscription.get("id")
    price_id = stripe_billing.extract_price_id(subscription)

    if event_type == "customer.subscription.deleted":
        user.subscription_status = "canceled"
        user.stripe_subscription_id = None
        user.stripe_price_id = None
        user.tier = "founder"
    else:
        user.subscription_status = status or "unknown"
        if isinstance(sub_id, str):
            user.stripe_subscription_id = sub_id
        if price_id:
            user.stripe_price_id = price_id
            new_tier = stripe_billing.tier_for_price(price_id)
            if new_tier and status in {"active", "trialing", "past_due"}:
                user.tier = new_tier

    await db.commit()
    return {"status": "ok", "subscription_status": user.subscription_status, "tier": user.tier}


async def _handle_payment_succeeded(db: AsyncSession, intent: dict[str, Any]) -> dict[str, Any]:
    """payment_intent.succeeded on a connected account = revenue. We log an
    event; daily/weekly rollups are aggregated from the event log.
    """
    account_id = str(intent.get("stripe_account") or intent.get("account") or "")
    if not account_id:
        return {"status": "ignored", "reason": "no connected account"}

    res = await db.execute(select(Business).where(Business.stripe_account_id == account_id))
    biz = res.scalar_one_or_none()
    if biz is None:
        return {"status": "ignored", "reason": "no business for account"}

    amount_cents = int(intent.get("amount_received") or intent.get("amount") or 0)
    session_id = await stripe_authorization._latest_session(db, biz.id)
    if session_id is not None:
        await event_log.write(
            db,
            session_id=session_id,
            business_id=biz.id,
            event_type="revenue_received",
            agent_name="stripe",
            payload={
                "amount_cents": amount_cents,
                "intent_id": intent.get("id"),
                "currency": intent.get("currency"),
            },
            cost_cents=-amount_cents,  # negative = inflow
        )
    return {"status": "ok", "business_id": str(biz.id), "amount_cents": amount_cents}

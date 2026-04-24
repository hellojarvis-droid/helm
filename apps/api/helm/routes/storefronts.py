"""Helm Storefront — first-party checkout pages at `/s/<slug>`.

Two surfaces:

    **Admin (auth-gated, per-business)**
      POST  /businesses/{id}/storefront        — create or update
      GET   /businesses/{id}/storefront        — read
      GET   /businesses/{id}/products          — list for this business
      POST  /businesses/{id}/products          — create a new SKU
      PATCH /businesses/{id}/products/{pid}    — edit a SKU
      DELETE /businesses/{id}/products/{pid}   — remove a SKU

    **Public (no auth)**
      GET   /s/{slug}                          — render storefront + live products
      POST  /s/{slug}/checkout                 — create a Stripe Checkout
                                                 Session on the connected
                                                 account, return its URL

Money flow uses Stripe Direct Charges — payment lands on the business's
connected account with no platform fee. We log a `revenue_received`
event when Stripe webhooks fire back on the completed payment.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import Business, HelmStorefront, Product
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.services import stripe_client
from helm.services.user_sync import sync_user_from_supabase

# Two routers so the public slug endpoints don't sit under /businesses.
admin_router = APIRouter(tags=["storefronts"])
public_router = APIRouter(tags=["storefronts_public"])

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])?$")


# ──────────────────────────────────────────────────────────
# Pydantic shapes
# ──────────────────────────────────────────────────────────


class StorefrontResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    slug: str
    title: str
    tagline: str | None
    theme: dict[str, Any]
    published: bool
    created_at: datetime
    updated_at: datetime


class ProductResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    sku: str | None
    name: str
    description: str | None
    price_cents: int
    compare_at_price_cents: int | None
    currency: str
    inventory_qty: int | None
    images: list[str]
    external_refs: dict[str, Any]
    published: bool
    created_at: datetime
    updated_at: datetime


class UpsertStorefrontRequest(BaseModel):
    slug: Annotated[str, Field(min_length=2, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    tagline: Annotated[str | None, Field(max_length=280)] = None
    theme: dict[str, Any] = Field(default_factory=dict)
    published: bool = False


class UpsertProductRequest(BaseModel):
    sku: Annotated[str | None, Field(max_length=64)] = None
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=8000)] = None
    price_cents: Annotated[int, Field(ge=0, le=10_000_000)]
    compare_at_price_cents: Annotated[int | None, Field(ge=0, le=10_000_000)] = None
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "usd"
    inventory_qty: Annotated[int | None, Field(ge=0)] = None
    images: list[str] = Field(default_factory=list)
    published: bool = False


class PatchProductRequest(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    price_cents: int | None = None
    compare_at_price_cents: int | None = None
    currency: str | None = None
    inventory_qty: int | None = None
    images: list[str] | None = None
    published: bool | None = None


class PublicStorefrontResponse(BaseModel):
    slug: str
    title: str
    tagline: str | None
    theme: dict[str, Any]
    business_name: str
    products: list[ProductResponse]


class CheckoutStartRequest(BaseModel):
    product_id: uuid.UUID
    quantity: Annotated[int, Field(ge=1, le=100)] = 1


class CheckoutStartResponse(BaseModel):
    url: str


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────


def _sf_to_response(row: HelmStorefront) -> StorefrontResponse:
    return StorefrontResponse(
        id=row.id,
        business_id=row.business_id,
        slug=row.slug,
        title=row.title,
        tagline=row.tagline,
        theme=row.theme,
        published=row.published,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _prod_to_response(row: Product) -> ProductResponse:
    return ProductResponse(
        id=row.id,
        business_id=row.business_id,
        sku=row.sku,
        name=row.name,
        description=row.description,
        price_cents=row.price_cents,
        compare_at_price_cents=row.compare_at_price_cents,
        currency=row.currency,
        inventory_qty=row.inventory_qty,
        images=list(row.images),
        external_refs=dict(row.external_refs),
        published=row.published,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_slug(raw: str) -> str:
    slug = raw.lower().strip()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail=(
                "slug must be lowercase letters, digits, and hyphens — "
                "start and end alphanumeric, 2-64 chars"
            ),
        )
    return slug


# ──────────────────────────────────────────────────────────
# Admin endpoints (auth required)
# ──────────────────────────────────────────────────────────


@admin_router.post(
    "/businesses/{business_id}/storefront",
    response_model=StorefrontResponse,
)
async def upsert_storefront(
    business_id: uuid.UUID,
    body: UpsertStorefrontRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StorefrontResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    slug = _normalize_slug(body.slug)

    # If another business already owns this slug, refuse — slugs are global.
    owner_q = await db.execute(
        select(HelmStorefront).where(HelmStorefront.slug == slug)
    )
    owner = owner_q.scalar_one_or_none()
    if owner is not None and owner.business_id != business_id:
        raise HTTPException(
            status_code=409,
            detail=f"slug '{slug}' is already in use by another Helm Storefront",
        )

    existing_q = await db.execute(
        select(HelmStorefront).where(HelmStorefront.business_id == business_id)
    )
    existing = existing_q.scalar_one_or_none()
    if existing is None:
        row = HelmStorefront(
            business_id=business_id,
            slug=slug,
            title=body.title,
            tagline=body.tagline,
            theme=body.theme,
            published=body.published,
        )
        db.add(row)
    else:
        row = existing
        row.slug = slug
        row.title = body.title
        row.tagline = body.tagline
        row.theme = body.theme
        row.published = body.published

    await db.commit()
    await db.refresh(row)
    return _sf_to_response(row)


@admin_router.get(
    "/businesses/{business_id}/storefront",
    response_model=StorefrontResponse,
)
async def get_storefront(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StorefrontResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row_q = await db.execute(
        select(HelmStorefront).where(HelmStorefront.business_id == business_id)
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="storefront not configured")
    return _sf_to_response(row)


@admin_router.get(
    "/businesses/{business_id}/products",
    response_model=list[ProductResponse],
)
async def list_products(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ProductResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    rows_q = await db.execute(
        select(Product)
        .where(Product.business_id == business_id)
        .order_by(Product.created_at.desc())
    )
    return [_prod_to_response(r) for r in rows_q.scalars().all()]


@admin_router.post(
    "/businesses/{business_id}/products",
    response_model=ProductResponse,
    status_code=201,
)
async def create_product(
    business_id: uuid.UUID,
    body: UpsertProductRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row = Product(
        business_id=business_id,
        sku=body.sku,
        name=body.name,
        description=body.description,
        price_cents=body.price_cents,
        compare_at_price_cents=body.compare_at_price_cents,
        currency=body.currency.lower(),
        inventory_qty=body.inventory_qty,
        images=body.images,
        published=body.published,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _prod_to_response(row)


@admin_router.patch(
    "/businesses/{business_id}/products/{product_id}",
    response_model=ProductResponse,
)
async def patch_product(
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    body: PatchProductRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row_q = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == business_id,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "currency" and isinstance(value, str):
            value = value.lower()
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return _prod_to_response(row)


@admin_router.delete(
    "/businesses/{business_id}/products/{product_id}",
    status_code=204,
)
async def delete_product(
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row_q = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == business_id,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────
# Public endpoints (no auth)
# ──────────────────────────────────────────────────────────


async def _load_public_storefront(
    db: AsyncSession, slug: str
) -> tuple[HelmStorefront, Business]:
    slug_norm = slug.lower().strip()
    sf_q = await db.execute(
        select(HelmStorefront).where(HelmStorefront.slug == slug_norm)
    )
    sf = sf_q.scalar_one_or_none()
    if sf is None or not sf.published:
        # Don't leak "exists-but-unpublished" vs "doesn't exist" — both 404.
        raise HTTPException(status_code=404, detail="storefront not found")
    biz = await db.get(Business, sf.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="storefront not found")
    return sf, biz


@public_router.get(
    "/s/{slug}",
    response_model=PublicStorefrontResponse,
    status_code=status.HTTP_200_OK,
)
async def get_public_storefront(
    slug: str,
    db: AsyncSession = Depends(get_session),
) -> PublicStorefrontResponse:
    sf, biz = await _load_public_storefront(db, slug)
    products_q = await db.execute(
        select(Product)
        .where(
            Product.business_id == sf.business_id,
            Product.published.is_(True),
        )
        .order_by(Product.created_at.desc())
    )
    products = [_prod_to_response(p) for p in products_q.scalars().all()]
    return PublicStorefrontResponse(
        slug=sf.slug,
        title=sf.title,
        tagline=sf.tagline,
        theme=sf.theme,
        business_name=biz.name,
        products=products,
    )


@public_router.post(
    "/s/{slug}/checkout",
    response_model=CheckoutStartResponse,
)
async def start_public_checkout(
    slug: str,
    body: CheckoutStartRequest,
    db: AsyncSession = Depends(get_session),
) -> CheckoutStartResponse:
    sf, biz = await _load_public_storefront(db, slug)
    if not biz.stripe_account_id:
        raise HTTPException(
            status_code=503,
            detail="this storefront isn't payment-ready yet — Stripe onboarding incomplete",
        )
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured on this deployment",
        )

    prod = await db.get(Product, body.product_id)
    if prod is None or prod.business_id != sf.business_id or not prod.published:
        raise HTTPException(status_code=404, detail="product not found")
    if prod.inventory_qty is not None and body.quantity > prod.inventory_qty:
        raise HTTPException(
            status_code=409,
            detail=f"only {prod.inventory_qty} in stock",
        )

    web = settings.web_base_url.rstrip("/")
    success_url = f"{web}/s/{sf.slug}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{web}/s/{sf.slug}?checkout=cancel"

    try:
        url = await stripe_client.create_direct_checkout_session(
            connected_account_id=biz.stripe_account_id,
            product_name=prod.name,
            unit_amount_cents=prod.price_cents,
            currency=prod.currency,
            quantity=body.quantity,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(prod.id),
            description=prod.description,
            image_urls=list(prod.images),
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"stripe checkout create failed: {e!s}",
        ) from e
    return CheckoutStartResponse(url=url)

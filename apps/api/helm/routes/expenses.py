"""Expenses + tax-export REST routes.

    GET  /businesses/{id}/expenses                 — list (filter by year, category)
    POST /businesses/{id}/expenses                 — create manual entry
    PATCH /expenses/{id}                           — edit category/vendor/description
    DELETE /expenses/{id}                          — remove
    GET  /businesses/{id}/expenses/export.csv      — tax-prep CSV
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import Expense
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["expenses"])

_CATEGORIES = (
    "advertising",
    "cogs",
    "software",
    "contractors",
    "travel",
    "meals",
    "utilities",
    "supplies",
    "legal",
    "bank_fees",
    "shipping",
    "other",
)


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    occurred_at: datetime
    amount_cents: int
    currency: str
    vendor: str
    category: str
    source: str
    source_ref: str | None
    description: str | None
    receipt_url: str | None
    meta: dict[str, Any]
    created_at: datetime


class CreateExpenseRequest(BaseModel):
    occurred_at: datetime
    amount_cents: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    vendor: str = Field(min_length=1, max_length=160)
    category: str = Field(pattern=r"^(advertising|cogs|software|contractors|travel|meals|utilities|supplies|legal|bank_fees|shipping|other)$")
    description: str | None = Field(default=None, max_length=1000)
    receipt_url: str | None = Field(default=None, max_length=2000)


class PatchExpenseRequest(BaseModel):
    vendor: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(
        default=None,
        pattern=r"^(advertising|cogs|software|contractors|travel|meals|utilities|supplies|legal|bank_fees|shipping|other)$",
    )
    description: str | None = Field(default=None, max_length=1000)
    receipt_url: str | None = Field(default=None, max_length=2000)


@router.get(
    "/businesses/{business_id}/expenses",
    response_model=list[ExpenseResponse],
)
async def list_expenses(
    business_id: uuid.UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    category: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ExpenseResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    stmt = (
        select(Expense)
        .where(Expense.business_id == business_id)
        .order_by(Expense.occurred_at.desc())
    )
    if year is not None:
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
        stmt = stmt.where(Expense.occurred_at >= start, Expense.occurred_at < end)
    if category:
        stmt = stmt.where(Expense.category == category)
    rows = list((await db.execute(stmt)).scalars().all())
    return [ExpenseResponse.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/businesses/{business_id}/expenses",
    response_model=ExpenseResponse,
    status_code=201,
)
async def create_expense(
    business_id: uuid.UUID,
    body: CreateExpenseRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ExpenseResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    row = Expense(
        business_id=business_id,
        occurred_at=body.occurred_at,
        amount_cents=body.amount_cents,
        currency=body.currency.upper(),
        vendor=body.vendor.strip(),
        category=body.category,
        source="manual",
        description=body.description,
        receipt_url=body.receipt_url,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return ExpenseResponse.model_validate(row, from_attributes=True)


async def _expense_for_user(
    db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID
) -> Expense:
    row = await db.get(Expense, expense_id)
    if row is None:
        raise HTTPException(status_code=404, detail="expense not found")
    biz = await get_business_for_user(db, user_id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="expense not found")
    return row


@router.patch(
    "/expenses/{expense_id}",
    response_model=ExpenseResponse,
)
async def patch_expense(
    expense_id: uuid.UUID,
    body: PatchExpenseRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ExpenseResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await _expense_for_user(db, user_row.id, expense_id)
    if body.vendor is not None:
        row.vendor = body.vendor.strip()
    if body.category is not None:
        row.category = body.category
    if body.description is not None:
        row.description = body.description
    if body.receipt_url is not None:
        row.receipt_url = body.receipt_url
    await db.commit()
    await db.refresh(row)
    return ExpenseResponse.model_validate(row, from_attributes=True)


@router.delete(
    "/expenses/{expense_id}",
    status_code=204,
)
async def delete_expense(
    expense_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    user_row = await sync_user_from_supabase(db, user)
    row = await _expense_for_user(db, user_row.id, expense_id)
    await db.delete(row)
    await db.commit()


@router.get("/businesses/{business_id}/expenses/export.csv")
async def export_expenses_csv(
    business_id: uuid.UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Tax-prep CSV. One row per expense, columns sized for a
    line-item schedule-C style export."""
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    stmt = (
        select(Expense)
        .where(Expense.business_id == business_id)
        .order_by(Expense.occurred_at.asc())
    )
    effective_year = year
    if effective_year is not None:
        start = datetime(effective_year, 1, 1, tzinfo=UTC)
        end = datetime(effective_year + 1, 1, 1, tzinfo=UTC)
        stmt = stmt.where(
            Expense.occurred_at >= start, Expense.occurred_at < end
        )
    rows = list((await db.execute(stmt)).scalars().all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "date",
            "vendor",
            "category",
            "amount",
            "currency",
            "source",
            "description",
            "receipt_url",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.occurred_at.date().isoformat(),
                r.vendor,
                r.category,
                f"{r.amount_cents / 100:.2f}",
                r.currency,
                r.source,
                (r.description or "").replace("\n", " "),
                r.receipt_url or "",
            ]
        )
    buf.seek(0)

    filename = f"{biz.name.replace(' ', '_')}_expenses"
    if effective_year is not None:
        filename += f"_{effective_year}"
    filename += ".csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Expose the category list so the UI can render a stable dropdown that
# matches the server's check constraint.
@router.get("/expense_categories")
async def list_expense_categories() -> list[str]:
    return list(_CATEGORIES)

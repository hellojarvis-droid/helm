"""One-click reformat — fan a MasterCreative out to N target formats.

For each target (platform + aspect), write a FormatRender row and a
re-laid-out Timeline JSON. A downstream renderer (Remotion worker,
wired in a later phase) reads `format_renders.status='pending'` and
produces the final MP4 at the target aspect.

Also updates `format_preferences` — when a user picks the same set of
targets 3+ times, the `times_seen` counter flips that set into an
"auto-suggested" state the UI can highlight so they don't have to
re-select the same 5 formats every campaign.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import (
    Campaign,
    FormatPreference,
    FormatRender,
    MasterCreative,
    SafeZone,
)

_PATTERN_THRESHOLD = 3


class MasterNotReadyError(Exception):
    """Source creative must have status='ready' before reformatting."""


async def reformat(
    db: AsyncSession,
    *,
    master_creative_id: uuid.UUID,
    targets: list[dict[str, str]],
) -> list[FormatRender]:
    """Create (or update) a FormatRender row per target.

    Each target is {'platform': 'instagram', 'aspect': '1:1',
    'mode': 'video'|'image'|'carousel'}. Existing rows are left alone
    unless they were `failed` — in which case they're reset to
    `pending` so the render worker retries.
    """
    master = await db.get(MasterCreative, master_creative_id)
    if master is None:
        raise ValueError(f"master creative {master_creative_id} not found")
    if master.status not in ("ready",):
        raise MasterNotReadyError(
            f"creative is {master.status} — reformat needs status='ready'"
        )

    results: list[FormatRender] = []
    for target in targets:
        platform = target.get("platform")
        aspect = target.get("aspect")
        mode = target.get("mode") or "video"
        if not platform or not aspect:
            continue

        existing_q = await db.execute(
            select(FormatRender).where(
                FormatRender.master_creative_id == master_creative_id,
                FormatRender.platform == platform,
                FormatRender.aspect == aspect,
            )
        )
        existing = existing_q.scalar_one_or_none()

        timeline = await _relayout_timeline(db, master, aspect=aspect)
        platform_copy = _platform_copy_for(master, platform)

        if existing is not None:
            if existing.status == "failed":
                existing.status = "pending"
                existing.error = None
            existing.platform_copy = platform_copy
            # Keep `output_url` if already rendered — no need to redo work.
            results.append(existing)
            continue

        row = FormatRender(
            master_creative_id=master_creative_id,
            platform=platform,
            aspect=aspect,
            mode=mode,
            status="pending",
            platform_copy={**platform_copy, "timeline_json": timeline},
        )
        db.add(row)
        results.append(row)

    # Track the chosen set as a format_preferences row (pattern learning).
    await _bump_pattern(
        db,
        business_id=await _business_id_for(db, master_creative_id),
        targets=targets,
    )

    await db.flush()
    return results


async def preferred_targets(
    db: AsyncSession, *, business_id: uuid.UUID
) -> list[list[dict[str, str]]]:
    """Return pattern sets the user has chosen >= threshold times.
    Sorted most-recent-first; UI can highlight the top entry as the
    "last used" suggestion."""
    q = await db.execute(
        select(FormatPreference)
        .where(
            FormatPreference.business_id == business_id,
            FormatPreference.times_seen >= _PATTERN_THRESHOLD,
        )
        .order_by(FormatPreference.last_seen_at.desc())
    )
    rows = list(q.scalars().all())
    return [_coerce_targets(list(r.pattern)) for r in rows]


async def _relayout_timeline(
    db: AsyncSession, master: MasterCreative, *, aspect: str
) -> dict[str, Any]:
    """Produce a Timeline JSON variant for a different aspect ratio.

    For v1 we copy the source timeline and overlay the new safe-zone
    insets — the real renderer (Remotion) reads these to crop/letterbox.
    """
    base = dict(master.timeline_json or {})
    width, height = _dimensions_for(aspect)
    base["aspect_ratio"] = aspect
    base["width"] = width
    base["height"] = height

    safe_q = await db.execute(
        select(SafeZone).where(SafeZone.aspect == aspect)
    )
    zones = [
        {
            "platform": z.platform,
            "top_pct": z.top_pct,
            "bottom_pct": z.bottom_pct,
            "left_pct": z.left_pct,
            "right_pct": z.right_pct,
        }
        for z in safe_q.scalars().all()
    ]
    base["safe_zones"] = zones
    return base


def _dimensions_for(aspect: str) -> tuple[int, int]:
    return {
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
        "4:5": (1080, 1350),
    }.get(aspect, (1080, 1920))


def _platform_copy_for(
    master: MasterCreative, platform: str
) -> dict[str, Any]:
    copy_bundle = dict(master.copy or {})
    copy_section = dict(copy_bundle.get("copy") or {})
    if platform == "tiktok":
        caption = (
            copy_section.get("caption_tiktok")
            or copy_section.get("caption_meta")
            or copy_section.get("headline")
            or ""
        )
    else:
        caption = (
            copy_section.get("caption_meta")
            or copy_section.get("caption_tiktok")
            or copy_section.get("headline")
            or ""
        )
    return {
        "caption": caption,
        "cta": copy_section.get("cta"),
        "headline": copy_section.get("headline"),
    }


async def _business_id_for(
    db: AsyncSession, master_creative_id: uuid.UUID
) -> uuid.UUID:
    q = await db.execute(
        select(Campaign.business_id)
        .join(MasterCreative, MasterCreative.campaign_id == Campaign.id)
        .where(MasterCreative.id == master_creative_id)
    )
    biz_id = q.scalar_one_or_none()
    if biz_id is None:
        raise ValueError(f"no business for creative {master_creative_id}")
    return biz_id


async def _bump_pattern(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    targets: list[dict[str, str]],
) -> None:
    pattern_hash, normalized = _hash_targets(targets)
    stmt = (
        insert(FormatPreference)
        .values(
            business_id=business_id,
            pattern_hash=pattern_hash,
            pattern=normalized,
        )
        .on_conflict_do_update(
            index_elements=["business_id", "pattern_hash"],
            set_={
                "times_seen": FormatPreference.times_seen + 1,
                "last_seen_at": insert(FormatPreference).excluded.created_at,
            },
        )
    )
    # Simpler and portable path: read-then-update if pattern exists.
    existing_q = await db.execute(
        select(FormatPreference).where(
            FormatPreference.business_id == business_id,
            FormatPreference.pattern_hash == pattern_hash,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        existing.times_seen = existing.times_seen + 1
        from datetime import UTC, datetime

        existing.last_seen_at = datetime.now(UTC)
    else:
        row = FormatPreference(
            business_id=business_id,
            pattern_hash=pattern_hash,
            pattern=normalized,
        )
        db.add(row)
    # `stmt` kept for future one-shot upsert migration; unused at runtime.
    _ = stmt


def _hash_targets(
    targets: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    normalized = _coerce_targets(list(targets))
    normalized.sort(key=lambda t: (t.get("platform", ""), t.get("aspect", "")))
    h = hashlib.sha1(
        json.dumps(normalized, sort_keys=True).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return h, normalized


def _coerce_targets(rows: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(
                {
                    "platform": str(r.get("platform", "")),
                    "aspect": str(r.get("aspect", "")),
                    "mode": str(r.get("mode", "video")),
                }
            )
    return out

"""Canvas Creative Studio routes.

    GET  /models                                    — model registry
    GET  /models/viral_presets                      — one-click viral prompts
    GET  /models/camera_presets                     — video camera chips
    POST /generations                               — kick off a generation
    GET  /generations/{id}                          — poll one
    GET  /generations?session_id=&tool=&business_id= — list (session / filters)
    POST /generations/{id}/favorite                 — toggle favorite
    POST /generations/{id}/action                   — "animate"/"upscale"/"edit" chip → new gen
    POST /generations/compare                       — parallel N-model run

    GET  /businesses/{id}/characters                — list
    POST /businesses/{id}/characters                — create (triggers stub training)
    DELETE /characters/{id}

    GET  /businesses/{id}/styles                    — list
    POST /businesses/{id}/styles                    — create
    DELETE /styles/{id}

    GET  /users/me/presets                          — list
    POST /users/me/presets                          — save
    DELETE /presets/{id}

    GET  /users/me/usage                            — per-model cost / count / avg latency
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import (
    Character,
    Generation,
    Preset,
    RenderJob,
    Style,
)
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import upstream_unavailable
from helm.services import credits, model_registry
from helm.services import generation as gen_service
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["canvas"])


# ──────────────────────────────────────────────────────────
# Model registry
# ──────────────────────────────────────────────────────────


class ModelEntryResponse(BaseModel):
    slug: str
    name: str
    provider: str
    modalities: list[str]
    cost_credits: int
    avg_seconds: int
    best_for: str
    description: str
    recommended_for: list[str]
    helm_managed: bool
    deprecated: bool


@router.get("/models", response_model=list[ModelEntryResponse])
async def list_models(tool: str | None = None) -> list[ModelEntryResponse]:
    entries = (
        model_registry.for_tool(tool)  # type: ignore[arg-type]
        if tool
        else model_registry.all_models()
    )
    return [
        ModelEntryResponse(
            slug=e.slug,
            name=e.name,
            provider=e.provider,
            modalities=list(e.modalities),
            cost_credits=e.cost_credits,
            avg_seconds=e.avg_seconds,
            best_for=e.best_for,
            description=e.description,
            recommended_for=list(e.recommended_for),
            helm_managed=e.helm_managed,
            deprecated=e.deprecated,
        )
        for e in entries
    ]


@router.get("/models/viral_presets")
async def list_viral_presets() -> list[dict[str, object]]:
    return [dict(p) for p in model_registry.VIRAL_PRESETS]


@router.get("/models/camera_presets")
async def list_camera_presets() -> list[dict[str, str]]:
    return [dict(p) for p in model_registry.CAMERA_MOTION_PRESETS]


# ──────────────────────────────────────────────────────────
# Generations
# ──────────────────────────────────────────────────────────


class ReferenceChip(BaseModel):
    url: str
    role: str = Field(
        pattern=r"^(character|style|describe|magic_fill|background_replace)$"
    )
    label: str | None = None


class CreateGenerationRequest(BaseModel):
    business_id: uuid.UUID | None = None
    session_id: uuid.UUID
    tool: str = Field(pattern=r"^(image|video|edit|enhance|lipsync)$")
    model: str
    prompt: str = Field(default="", max_length=4000)
    params: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceChip] = Field(default_factory=list)
    parent_generation_id: uuid.UUID | None = None


class GenerationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    session_id: uuid.UUID
    parent_generation_id: uuid.UUID | None
    tool: str
    model: str
    prompt: str
    params: dict[str, Any]
    references: list[dict[str, Any]]
    status: str
    output_url: str | None
    thumbnail_url: str | None
    cost_cents_reserved: int | None
    cost_cents_actual: int | None
    error: str | None
    favorited: bool
    created_at: datetime
    updated_at: datetime


@router.post("/generations", response_model=GenerationResponse, status_code=201)
async def create_generation(
    body: CreateGenerationRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    user_row = await sync_user_from_supabase(db, user)
    business_id = body.business_id
    if business_id is not None:
        biz = await get_business_for_user(db, user_row.id, business_id)
        if biz is None:
            raise HTTPException(status_code=404, detail="business not found")

    try:
        gen = await gen_service.create(
            db,
            user_id=user_row.id,
            business_id=business_id,
            session_id=body.session_id,
            tool=body.tool,
            model=body.model,
            prompt=body.prompt,
            params=body.params,
            references=[r.model_dump() for r in body.references],
            parent_generation_id=body.parent_generation_id,
        )
    except credits.InsufficientCreditsError as e:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "needed_cents": e.needed_cents,
                "balance_cents": e.balance_cents,
                "message": "Top up credits to continue.",
            },
        ) from e
    except gen_service.GenerationError as e:
        raise upstream_unavailable("The generation service") from e

    await db.refresh(gen)
    return GenerationResponse.model_validate(gen, from_attributes=True)


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    user_row = await sync_user_from_supabase(db, user)
    gen = await _gen_for_user(db, user_row.id, generation_id)
    return GenerationResponse.model_validate(gen, from_attributes=True)


@router.get("/generations", response_model=list[GenerationResponse])
async def list_generations(
    session_id: uuid.UUID | None = None,
    tool: str | None = None,
    business_id: uuid.UUID | None = None,
    favorited: bool | None = None,
    limit: int = 200,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[GenerationResponse]:
    user_row = await sync_user_from_supabase(db, user)
    stmt = (
        select(Generation)
        .where(Generation.user_id == user_row.id)
        .order_by(desc(Generation.created_at))
        .limit(max(1, min(limit, 500)))
    )
    if session_id is not None:
        stmt = stmt.where(Generation.session_id == session_id)
    if tool:
        stmt = stmt.where(Generation.tool == tool)
    if business_id is not None:
        stmt = stmt.where(Generation.business_id == business_id)
    if favorited is not None:
        stmt = stmt.where(Generation.favorited == favorited)
    rows = list((await db.execute(stmt)).scalars().all())
    return [GenerationResponse.model_validate(r, from_attributes=True) for r in rows]


@router.post("/generations/{generation_id}/favorite", response_model=GenerationResponse)
async def toggle_favorite(
    generation_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    user_row = await sync_user_from_supabase(db, user)
    gen = await _gen_for_user(db, user_row.id, generation_id)
    gen.favorited = not gen.favorited
    await db.commit()
    await db.refresh(gen)
    return GenerationResponse.model_validate(gen, from_attributes=True)


class ActionRequest(BaseModel):
    """'Use' action on an existing generation → spawns new generation."""

    action: str = Field(pattern=r"^(animate|lipsync|edit|upscale|use_as_reference)$")
    prompt: str | None = Field(default=None, max_length=4000)
    params: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


@router.post("/generations/{generation_id}/action", response_model=GenerationResponse)
async def run_action(
    generation_id: uuid.UUID,
    body: ActionRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    """Spawn a follow-up generation from an existing output.

    Maps the action → (tool, default model):
        animate      → video, Recommended video model
        lipsync      → lipsync, Recommended lipsync model
        edit         → edit, Recommended edit model
        upscale      → enhance, Recommended enhance model
        use_as_reference → no-op, returns source (caller attaches it themselves)
    """
    user_row = await sync_user_from_supabase(db, user)
    source = await _gen_for_user(db, user_row.id, generation_id)
    if source.output_url is None:
        raise HTTPException(
            status_code=409, detail="source generation has no output yet"
        )

    if body.action == "use_as_reference":
        return GenerationResponse.model_validate(source, from_attributes=True)

    action_to_tool: dict[str, str] = {
        "animate": "video",
        "lipsync": "lipsync",
        "edit": "edit",
        "upscale": "enhance",
    }
    tool = action_to_tool[body.action]
    model = body.model or (
        entry.slug
        if (entry := model_registry.recommended(tool))  # type: ignore[arg-type]
        else None
    )
    if not model:
        raise HTTPException(status_code=500, detail=f"no recommended model for {tool}")

    # Auto-attach the source as a reference so the downstream adapter
    # uses it as seed/character/style.
    role = {
        "animate": "describe",
        "lipsync": "describe",
        "edit": "magic_fill",
        "upscale": "describe",
    }[body.action]
    refs = [{"url": source.output_url, "role": role}]

    try:
        gen = await gen_service.create(
            db,
            user_id=user_row.id,
            business_id=source.business_id,
            session_id=source.session_id,
            tool=tool,
            model=model,
            prompt=body.prompt or source.prompt,
            params=body.params,
            references=refs,
            parent_generation_id=source.id,
        )
    except credits.InsufficientCreditsError as e:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "needed_cents": e.needed_cents,
                "balance_cents": e.balance_cents,
            },
        ) from e
    except gen_service.GenerationError as e:
        raise upstream_unavailable("The generation service") from e
    await db.refresh(gen)
    return GenerationResponse.model_validate(gen, from_attributes=True)


class CompareRequest(BaseModel):
    business_id: uuid.UUID | None = None
    session_id: uuid.UUID
    tool: str = Field(pattern=r"^(image|video|edit|enhance|lipsync)$")
    models: list[str] = Field(min_length=2, max_length=4)
    prompt: str = Field(max_length=4000)
    params: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceChip] = Field(default_factory=list)


@router.post("/generations/compare", response_model=list[GenerationResponse])
async def compare(
    body: CompareRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[GenerationResponse]:
    """Same prompt across N models in parallel. Returns N generation
    rows — client polls each until terminal."""
    user_row = await sync_user_from_supabase(db, user)
    if body.business_id is not None:
        biz = await get_business_for_user(db, user_row.id, body.business_id)
        if biz is None:
            raise HTTPException(status_code=404, detail="business not found")

    async def _one(model: str) -> Generation:
        try:
            return await gen_service.create(
                db,
                user_id=user_row.id,
                business_id=body.business_id,
                session_id=body.session_id,
                tool=body.tool,
                model=model,
                prompt=body.prompt,
                params=body.params,
                references=[r.model_dump() for r in body.references],
            )
        except credits.InsufficientCreditsError:
            raise
        except gen_service.GenerationError as e:
            raise upstream_unavailable("The generation service") from e

    # Sequential rather than gather() to keep one DB session per hit
    # (asyncpg still can't serve concurrent ops on one connection).
    gens: list[Generation] = []
    for m in body.models:
        try:
            gens.append(await _one(m))
        except credits.InsufficientCreditsError as e:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "needed_cents": e.needed_cents,
                    "balance_cents": e.balance_cents,
                },
            ) from e
    for g in gens:
        await db.refresh(g)
    return [GenerationResponse.model_validate(g, from_attributes=True) for g in gens]


async def _gen_for_user(
    db: AsyncSession, user_id: uuid.UUID, gen_id: uuid.UUID
) -> Generation:
    gen = await db.get(Generation, gen_id)
    if gen is None or gen.user_id != user_id:
        raise HTTPException(status_code=404, detail="generation not found")
    return gen


# ──────────────────────────────────────────────────────────
# Characters
# ──────────────────────────────────────────────────────────


class CharacterResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    reference_image_urls: list[str]
    trained_provider: str | None
    trained_ref_id: str | None
    status: str
    meta: dict[str, Any]
    created_at: datetime


class CreateCharacterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    reference_image_urls: list[str] = Field(min_length=1, max_length=12)


@router.get(
    "/businesses/{business_id}/characters",
    response_model=list[CharacterResponse],
)
async def list_characters(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[CharacterResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    q = await db.execute(
        select(Character)
        .where(Character.business_id == business_id)
        .order_by(desc(Character.created_at))
    )
    return [
        CharacterResponse.model_validate(r, from_attributes=True)
        for r in q.scalars().all()
    ]


@router.post(
    "/businesses/{business_id}/characters",
    response_model=CharacterResponse,
    status_code=201,
)
async def create_character(
    business_id: uuid.UUID,
    body: CreateCharacterRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> CharacterResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row = Character(
        business_id=business_id,
        name=body.name.strip(),
        reference_image_urls=list(body.reference_image_urls),
        status="untrained",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CharacterResponse.model_validate(row, from_attributes=True)


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character(
    character_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(Character, character_id)
    if row is None:
        raise HTTPException(status_code=404, detail="character not found")
    biz = await get_business_for_user(db, user_row.id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="character not found")
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────
# Styles
# ──────────────────────────────────────────────────────────


class StyleResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    reference_image_urls: list[str]
    palette: dict[str, Any]
    notes: str | None
    created_at: datetime


class CreateStyleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    reference_image_urls: list[str] = Field(default_factory=list, max_length=12)
    palette: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/businesses/{business_id}/styles", response_model=list[StyleResponse])
async def list_styles(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[StyleResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    q = await db.execute(
        select(Style)
        .where(Style.business_id == business_id)
        .order_by(desc(Style.created_at))
    )
    return [StyleResponse.model_validate(r, from_attributes=True) for r in q.scalars().all()]


@router.post(
    "/businesses/{business_id}/styles",
    response_model=StyleResponse,
    status_code=201,
)
async def create_style(
    business_id: uuid.UUID,
    body: CreateStyleRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StyleResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row = Style(
        business_id=business_id,
        name=body.name.strip(),
        reference_image_urls=list(body.reference_image_urls),
        palette=body.palette,
        notes=body.notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return StyleResponse.model_validate(row, from_attributes=True)


@router.delete("/styles/{style_id}", status_code=204)
async def delete_style(
    style_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(Style, style_id)
    if row is None:
        raise HTTPException(status_code=404, detail="style not found")
    biz = await get_business_for_user(db, user_row.id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="style not found")
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────
# Presets
# ──────────────────────────────────────────────────────────


class PresetResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    tool: str
    model: str
    params: dict[str, Any]
    prompt_template: str | None
    created_at: datetime


class CreatePresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    tool: str = Field(pattern=r"^(image|video|edit|enhance|lipsync)$")
    model: str
    params: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str | None = Field(default=None, max_length=2000)


@router.get("/users/me/presets", response_model=list[PresetResponse])
async def list_presets(
    tool: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[PresetResponse]:
    user_row = await sync_user_from_supabase(db, user)
    stmt = (
        select(Preset)
        .where(Preset.user_id == user_row.id)
        .order_by(desc(Preset.created_at))
    )
    if tool:
        stmt = stmt.where(Preset.tool == tool)
    rows = list((await db.execute(stmt)).scalars().all())
    return [PresetResponse.model_validate(r, from_attributes=True) for r in rows]


@router.post("/users/me/presets", response_model=PresetResponse, status_code=201)
async def create_preset(
    body: CreatePresetRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PresetResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = Preset(
        user_id=user_row.id,
        name=body.name.strip(),
        tool=body.tool,
        model=body.model,
        params=body.params,
        prompt_template=body.prompt_template,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return PresetResponse.model_validate(row, from_attributes=True)


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(Preset, preset_id)
    if row is None or row.user_id != user_row.id:
        raise HTTPException(status_code=404, detail="preset not found")
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────
# Usage dashboard
# ──────────────────────────────────────────────────────────


class UsageAggregate(BaseModel):
    tool: str
    model: str
    count: int
    total_cost_cents: int
    avg_seconds: float | None
    last_used: datetime | None


class UsageResponse(BaseModel):
    totals: dict[str, int]
    per_model: list[UsageAggregate]


@router.get("/users/me/usage", response_model=UsageResponse)
async def usage(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> UsageResponse:
    user_row = await sync_user_from_supabase(db, user)
    agg_q = await db.execute(
        select(
            Generation.tool,
            Generation.model,
            func.count().label("c"),
            func.coalesce(func.sum(Generation.cost_cents_actual), 0).label("cost"),
            func.max(Generation.created_at).label("last"),
        )
        .where(Generation.user_id == user_row.id)
        .group_by(Generation.tool, Generation.model)
        .order_by(desc(func.count()))
    )
    rows = list(agg_q.all())

    # Average render latency per (provider, mode) from the underlying
    # render_jobs — rougher but richer than re-walking generations.
    lat_q = await db.execute(
        select(
            RenderJob.provider,
            RenderJob.mode,
            func.avg(
                func.extract(
                    "epoch", RenderJob.completed_at - RenderJob.started_at
                )
            ).label("avg_seconds"),
        )
        .where(
            RenderJob.user_id == user_row.id,
            RenderJob.status == "completed",
            RenderJob.started_at.isnot(None),
            RenderJob.completed_at.isnot(None),
        )
        .group_by(RenderJob.provider, RenderJob.mode)
    )
    lat_by_provider = {(r.provider, r.mode): float(r.avg_seconds or 0) for r in lat_q.all()}

    per_model: list[UsageAggregate] = []
    total_count = 0
    total_cost = 0
    for r in rows:
        entry = model_registry.get(r.tool, r.model)
        provider = entry.provider if entry else r.model
        # Pick the most likely mode key based on tool.
        mode_key = {"image": "image", "video": "video", "edit": "image", "enhance": "image", "lipsync": "video"}.get(r.tool, "image")
        avg_s = lat_by_provider.get((provider, mode_key))
        per_model.append(
            UsageAggregate(
                tool=r.tool,
                model=r.model,
                count=r.c,
                total_cost_cents=int(r.cost or 0),
                avg_seconds=avg_s,
                last_used=r.last,
            )
        )
        total_count += r.c
        total_cost += int(r.cost or 0)

    # avoid unused asyncio import warning — compare uses it internally
    _ = asyncio
    return UsageResponse(
        totals={"count": total_count, "cost_cents": total_cost},
        per_model=per_model,
    )

"""POST /chat — SSE-streamed CEO Agent conversation.

Client sends `{ "message": "...", "business_id": "<uuid>" | null }`; server
streams NDJSON-shaped SSE events for every runtime event. The connection
stays open for the lifetime of the turn.

Each SSE `data:` line is a JSON object `{"kind": "<EventKind>", ...}`. See
`helm.agents.runtime.ChatEvent` for the schema.

POST /chat/transcribe accepts a multipart audio upload and returns the
text via OpenAI Whisper. Used by the mobile mic button.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.runtime import default_runtime
from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import AgentEvent
from helm.db.session import get_session, session_scope
from helm.db.tenant import get_business_for_user
from helm.errors import ClientError
from helm.services import sessions
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/chat", tags=["chat"])
log = structlog.get_logger("helm.chat")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    business_id: uuid.UUID | None = Field(
        default=None,
        description="Business scope for this turn. Null = orchestrator / cross-business.",
    )


class ChatHistoryItem(BaseModel):
    id: int
    kind: str
    role: str | None = None
    text: str | None = None
    business_id: uuid.UUID | None = None
    created_at: datetime
    payload: dict[str, Any]
    approval: dict[str, Any] | None = None


class ChatHistoryResponse(BaseModel):
    session_id: uuid.UUID
    items: list[ChatHistoryItem]


_HISTORY_EVENT_TYPES = (
    "message.user",
    "message.agent",
    "tool_call",
    "tool_result",
    "specialist_completed",
    "approval_requested",
    "approval_approved",
    "approval_modified",
    "approval_denied",
    "approval_expired",
    "launch_started",
    "launch_step_completed",
    "launch_step_skipped",
    "launch_step_failed",
    "launch_completed",
    "launch_failed",
)


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    business_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ChatHistoryResponse:
    """Return the user's persistent Atlas thread for web/mobile hydration."""
    user_row = await sync_user_from_supabase(db, user)
    if business_id is not None:
        biz = await get_business_for_user(db, user_row.id, business_id)
        if biz is None:
            raise HTTPException(status_code=404, detail="business not found")

    session = await sessions.get_or_create_ceo_session(db, user_row.id)
    stmt = (
        select(AgentEvent)
        .where(
            AgentEvent.session_id == session.id,
            AgentEvent.event_type.in_(_HISTORY_EVENT_TYPES),
        )
        .order_by(AgentEvent.id.desc())
        .limit(limit)
    )
    if business_id is not None:
        stmt = stmt.where(AgentEvent.business_id == business_id)

    rows = list(reversed((await db.execute(stmt)).scalars().all()))
    return ChatHistoryResponse(
        session_id=session.id,
        items=[_history_item(row) for row in rows],
    )


@router.post("")
async def post_chat(
    body: ChatRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    user_row = await sync_user_from_supabase(db, user)

    if body.business_id is not None:
        biz = await get_business_for_user(db, user_row.id, body.business_id)
        if biz is None:
            # Fail closed — tenant isolation. Don't leak existence vs access.
            raise HTTPException(status_code=404, detail="business not found")

    session = await sessions.get_or_create_ceo_session(db, user_row.id)
    # Capture the handles we need from the request-scoped session, then open
    # a fresh session inside the generator — `Depends(get_session)` closes
    # when the handler returns, which happens *before* the stream body runs.
    user_id = user_row.id
    business_id = body.business_id
    session_id = session.id
    message = body.message

    async def event_stream() -> AsyncIterator[str]:
        async with session_scope() as streaming_db:
            runtime = default_runtime()
            async for event in runtime.stream_turn(
                streaming_db,
                session_id=session_id,
                user_id=user_id,
                business_id=business_id,
                user_message=message,
            ):
                yield event.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable buffering in proxies (nginx/render)
        },
    )


def _history_item(row: AgentEvent) -> ChatHistoryItem:
    payload = dict(row.payload or {})
    role: str | None = None
    text: str | None = None
    approval: dict[str, Any] | None = None

    if row.event_type == "message.user":
        role = "user"
        text = _payload_text(payload)
    elif row.event_type == "message.agent":
        role = "agent"
        text = _payload_text(payload)
    elif row.event_type.startswith("approval_"):
        approval = {
            "approval_id": payload.get("approval_id"),
            "kind": payload.get("kind"),
            "summary": payload.get("summary"),
            "status": row.event_type.removeprefix("approval_"),
            "modifications": payload.get("modifications"),
        }
        text = payload.get("summary") if isinstance(payload.get("summary"), str) else None
    elif row.event_type == "tool_call":
        name = payload.get("name")
        text = f"Called {name}" if isinstance(name, str) else None
    elif row.event_type == "tool_result":
        name = payload.get("name")
        is_error = payload.get("is_error")
        if isinstance(name, str):
            text = f"{name} {'failed' if is_error else 'completed'}"
    elif row.event_type == "specialist_completed":
        summary = payload.get("summary")
        text = summary if isinstance(summary, str) else None

    return ChatHistoryItem(
        id=row.id,
        kind=row.event_type,
        role=role,
        text=text,
        business_id=row.business_id,
        created_at=row.created_at,
        payload=payload,
        approval=approval,
    )


def _payload_text(payload: dict[str, Any]) -> str:
    raw = payload.get("text")
    if isinstance(raw, str) and raw.strip():
        return raw
    blocks = payload.get("content_blocks")
    if isinstance(blocks, list):
        parts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(part for part in parts if isinstance(part, str))
    return ""


class TranscribeResponse(BaseModel):
    text: str


_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Whisper API cap


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> TranscribeResponse:
    """Transcribe a short voice memo via OpenAI Whisper. Best-effort: missing
    OPENAI_API_KEY returns 501 so the client can hide the mic button.

    Tenant-scoped (require_user) so we don't let the endpoint be an open
    relay to OpenAI on our quota.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=501, detail="transcription not configured")

    # Confirm the user row exists (defense-in-depth + populates user_sync).
    await sync_user_from_supabase(db, user)

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(raw) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio exceeds 25 MB limit")

    # Call Whisper in a thread — the SDK is sync.
    from openai import OpenAI

    def _call() -> str:
        client = OpenAI(api_key=settings.openai_api_key)
        # The API wants a file-like with a filename for format detection.
        buf = io.BytesIO(raw)
        buf.name = audio.filename or "audio.m4a"
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            response_format="text",
        )
        return str(result).strip()

    try:
        text = await asyncio.to_thread(_call)
    except Exception as e:  # surface as 502 so the client can retry
        log.warning("chat.transcribe_failed", err=str(e)[:300])
        raise ClientError(
            "transcription_failed",
            status_code=502,
            message=("Voice transcription failed. Try recording again, or type your message."),
        ) from e

    return TranscribeResponse(text=text)

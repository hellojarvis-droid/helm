"""POST /chat — SSE-streamed CEO Agent conversation.

Client sends `{ "message": "...", "business_id": "<uuid>" | null }`; server
streams NDJSON-shaped SSE events for every runtime event. The connection
stays open for the lifetime of the turn.

Each SSE `data:` line is a JSON object `{"kind": "<EventKind>", ...}`. See
`helm.agents.runtime.ChatEvent` for the schema.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.runtime import default_runtime
from helm.auth import CurrentUser, require_user
from helm.db.session import get_session, session_scope
from helm.db.tenant import get_business_for_user
from helm.services import sessions
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    business_id: uuid.UUID | None = Field(
        default=None,
        description="Business scope for this turn. Null = orchestrator / cross-business.",
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

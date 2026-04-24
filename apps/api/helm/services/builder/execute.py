"""Execute layer — apply an approved Plan as file operations.

Sonnet 4.6 generates the file ops. We send the plan + the full current
file tree (truncating any single file to a safe ceiling). The model
returns a JSON array of `{op, path, content?}` entries.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from helm.services.builder import _llm
from helm.services.builder.prompts import EXECUTE_SYSTEM

_MODEL = "claude-sonnet-4-6"
_PER_FILE_CHAR_CAP = 60_000
_TOTAL_CHAR_CAP = 400_000


class FileOp(TypedDict, total=False):
    op: Literal["write", "delete"]
    path: str
    content: str


class ExecuteResult(TypedDict):
    ops: list[FileOp]
    logs: str
    model_used: str


async def apply(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    user_id: uuid.UUID,
    plain_plan: str,
    technical_plan: str,
    file_hints: list[str],
    files: dict[str, str],
) -> ExecuteResult:
    """Ask the LLM for file ops. Returns a list; caller (orchestrator)
    validates paths and applies via versioning.commit_changes."""
    # Prune the context: preserve the full content of file_hints
    # first, then fill remaining budget with other paths truncated.
    trimmed = _trim_files(files, preferred=file_hints)
    user_message = json.dumps(
        {
            "plan": plain_plan,
            "technical_plan": technical_plan,
            "file_hints": file_hints,
            "files": trimmed,
        },
        indent=2,
    )

    parsed = await _llm.run_step(
        db,
        project_id=project_id,
        plan_id=plan_id,
        user_id=user_id,
        step="execute",
        model=_MODEL,
        system=EXECUTE_SYSTEM,
        user_message=user_message,
        estimate_cents=30,
        max_tokens=6000,
    )
    if not isinstance(parsed, list):
        raise _llm.BuilderLLMError("execute: expected JSON array of ops")

    ops: list[FileOp] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        op = str(entry.get("op", "")).lower()
        path = str(entry.get("path", "")).strip()
        if not path or op not in ("write", "delete"):
            continue
        if op == "write":
            content = entry.get("content")
            if not isinstance(content, str):
                continue
            ops.append({"op": "write", "path": path, "content": content})
        else:
            ops.append({"op": "delete", "path": path, "content": ""})
    return {"ops": ops, "logs": f"executed {len(ops)} op(s) with {_MODEL}", "model_used": _MODEL}


def _trim_files(files: dict[str, str], *, preferred: list[str]) -> dict[str, str]:
    """Keep preferred paths full-content; truncate the rest to fit budget."""
    out: dict[str, str] = {}
    budget = _TOTAL_CHAR_CAP
    preferred_set = set(preferred)
    for path in preferred:
        content = files.get(path)
        if content is None:
            continue
        c = content[:_PER_FILE_CHAR_CAP]
        if len(c) + 100 < budget:
            out[path] = c
            budget -= len(c)
    for path, content in files.items():
        if path in preferred_set or path in out:
            continue
        c = content
        if len(c) > 4000:
            c = c[:2000] + "\n/* …truncated… */\n" + c[-1000:]
        if len(c) + 100 >= budget:
            continue
        out[path] = c
        budget -= len(c)
    return out

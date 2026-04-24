"""Version + snapshot management for Builder.

Every execute.apply() is wrapped in a snapshot pair:
  1. `snapshot()` records the current file tree as a new Version and
     sets `project.previous_version_id = project.current_version_id`.
  2. Execute writes new files under the new version.
  3. On failure we call `rollback_last()` to restore the previous state.
  4. User's "Undo" button calls `undo_last()` — same effect.

Simple, safe, one-step-deep. No branching, no merge — that's v2.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import BuilderProject, BuilderProjectFile, BuilderVersion

log = structlog.get_logger("helm.builder.versioning")


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: str
    content: str
    binary_url: str | None
    hash: str


async def load_files(
    db: AsyncSession, *, project_id: uuid.UUID, version_id: uuid.UUID | None = None
) -> list[FileSnapshot]:
    """Load file rows for a specific version (defaults to current)."""
    proj = await db.get(BuilderProject, project_id)
    if proj is None:
        return []
    vid = version_id or proj.current_version_id
    if vid is None:
        return []
    q = await db.execute(
        select(BuilderProjectFile).where(BuilderProjectFile.version_id == vid)
    )
    rows = list(q.scalars().all())
    return [
        FileSnapshot(
            path=r.path, content=r.content, binary_url=r.binary_url, hash=r.hash
        )
        for r in rows
    ]


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


async def snapshot(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    label: str | None = None,
    change_summary_plain: str | None = None,
    change_summary_technical: str | None = None,
) -> BuilderVersion:
    """Write a new BuilderVersion copying the current file tree. Returns
    the new version row. Does NOT flip `current_version_id` — caller
    does that after execute writes the new file rows against this
    version id.
    """
    proj = await db.get(BuilderProject, project_id)
    if proj is None:
        raise ValueError(f"builder project {project_id} not found")

    parent_id = proj.current_version_id
    manifest: dict[str, str] = {}
    if parent_id is not None:
        q = await db.execute(
            select(BuilderProjectFile).where(BuilderProjectFile.version_id == parent_id)
        )
        for f in q.scalars().all():
            manifest[f.path] = f.hash

    version = BuilderVersion(
        project_id=project_id,
        parent_version_id=parent_id,
        label=label,
        change_summary_plain=change_summary_plain,
        change_summary_technical=change_summary_technical,
        snapshot_manifest=manifest,
    )
    db.add(version)
    await db.flush()

    # Copy parent's file rows forward so the new version starts as a
    # duplicate of the previous state. Execute then overwrites touched
    # paths; untouched files roll forward unchanged.
    if parent_id is not None:
        parent_files_q = await db.execute(
            select(BuilderProjectFile).where(BuilderProjectFile.version_id == parent_id)
        )
        for src in parent_files_q.scalars().all():
            db.add(
                BuilderProjectFile(
                    project_id=project_id,
                    version_id=version.id,
                    path=src.path,
                    content=src.content,
                    binary_url=src.binary_url,
                    hash=src.hash,
                )
            )
    await db.flush()
    return version


async def write_initial(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    files: dict[str, str],
    label: str = "initial",
) -> BuilderVersion:
    """Seed a brand-new project's first version (no parent). Used for
    blank templates and imports."""
    version = BuilderVersion(
        project_id=project_id,
        parent_version_id=None,
        label=label,
        snapshot_manifest={p: hash_content(c) for p, c in files.items()},
    )
    db.add(version)
    await db.flush()
    for path, content in files.items():
        db.add(
            BuilderProjectFile(
                project_id=project_id,
                version_id=version.id,
                path=path,
                content=content,
                hash=hash_content(content),
            )
        )
    await db.flush()
    proj = await db.get(BuilderProject, project_id)
    if proj is not None:
        proj.current_version_id = version.id
        proj.previous_version_id = None
    return version


async def commit_changes(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    new_version_id: uuid.UUID,
    writes: dict[str, str],
    deletes: list[str],
) -> None:
    """Apply file-level operations to an already-created version row
    (produced by `snapshot`). Writes overwrite paths; deletes remove rows.
    """
    if writes:
        existing_q = await db.execute(
            select(BuilderProjectFile).where(
                BuilderProjectFile.version_id == new_version_id,
                BuilderProjectFile.path.in_(list(writes.keys())),
            )
        )
        by_path = {f.path: f for f in existing_q.scalars().all()}
        for path, content in writes.items():
            h = hash_content(content)
            if path in by_path:
                row = by_path[path]
                row.content = content
                row.hash = h
            else:
                db.add(
                    BuilderProjectFile(
                        project_id=project_id,
                        version_id=new_version_id,
                        path=path,
                        content=content,
                        hash=h,
                    )
                )
    if deletes:
        del_q = await db.execute(
            select(BuilderProjectFile).where(
                BuilderProjectFile.version_id == new_version_id,
                BuilderProjectFile.path.in_(deletes),
            )
        )
        for row in del_q.scalars().all():
            await db.delete(row)
    await db.flush()


async def finalize(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    new_version_id: uuid.UUID,
) -> None:
    """Move the project's `current_version_id` to `new_version_id` and
    slide its previous_version_id pointer. Call after commit_changes
    succeeds.
    """
    proj = await db.get(BuilderProject, project_id)
    if proj is None:
        return
    proj.previous_version_id = proj.current_version_id
    proj.current_version_id = new_version_id
    await db.flush()


async def undo_last(db: AsyncSession, *, project_id: uuid.UUID) -> BuilderVersion | None:
    """One-step undo: revert to previous_version_id if set."""
    proj = await db.get(BuilderProject, project_id)
    if proj is None or proj.previous_version_id is None:
        return None
    prev_id = proj.previous_version_id
    prev = await db.get(BuilderVersion, prev_id)
    if prev is None:
        return None
    # Slide pointers: current → prev, previous → prev.parent (or None).
    proj.current_version_id = prev_id
    proj.previous_version_id = prev.parent_version_id
    await db.flush()
    log.info(
        "builder.versioning.undo",
        project_id=str(project_id),
        reverted_to=str(prev_id),
    )
    return prev

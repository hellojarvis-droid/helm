"""Publish Builder projects.

v1 scope:
- Static projects: freeze the current file tree into a publish-marked
  version + set `published_url = /apps/{slug}`. The public route reads
  the version's files straight from the DB and serves index.html.
- Vite / Next / React (CRA): same flow, but the preview's WebContainer
  produces a build bundle in-browser at preview time. The publisher
  captures the current file tree (source) as the published version;
  serving a built bundle is a post-v1 follow-up that requires
  server-side build or a browser-upload step. For now we serve the
  source files, which works for static-exported Next + Vite dev output
  and degrades clearly for server-rendered paths.

Custom-domain issuance is a stub that persists the domain + returns
CNAME instructions. Automated TLS via Let's Encrypt lands in a
post-v1 task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import (
    BuilderProject,
    BuilderProjectFile,
    BuilderVersion,
)


class PublishError(Exception):
    """Routes convert this to 4xx."""


async def publish_helm_hosted(
    db: AsyncSession, *, project_id: uuid.UUID
) -> BuilderProject:
    """Freeze the current version + stamp a public URL."""
    project = await db.get(BuilderProject, project_id)
    if project is None:
        raise PublishError("project not found")
    if project.current_version_id is None:
        raise PublishError("project has no files yet — make a change first")

    # Check there's an index.html somewhere so /apps/{slug} has content.
    q = await db.execute(
        select(BuilderProjectFile.path).where(
            BuilderProjectFile.version_id == project.current_version_id
        )
    )
    paths = [row[0] for row in q.all()]
    if not any(p == "index.html" or p.endswith("/index.html") for p in paths):
        raise PublishError(
            "Your project needs an index.html at the root — ask Builder to add one."
        )

    # Label the current version as the published one.
    version = await db.get(BuilderVersion, project.current_version_id)
    if version is not None:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        version.label = f"published@{stamp}"

    project.published_url = f"/apps/{project.slug}"
    project.status = "published"
    project.updated_at = datetime.now(UTC)
    await db.flush()
    return project


async def request_custom_domain(
    db: AsyncSession, *, project_id: uuid.UUID, domain: str
) -> dict[str, Any]:
    """Persist the user-owned custom domain and return the CNAME
    record they need to configure on their DNS provider.

    v1 is a stub: we don't automatically provision TLS. The payload
    tells the founder exactly which record to add.
    """
    project = await db.get(BuilderProject, project_id)
    if project is None:
        raise PublishError("project not found")
    cleaned = domain.strip().lower()
    if not cleaned or " " in cleaned or "/" in cleaned:
        raise PublishError("That doesn't look like a valid domain.")
    project.custom_domain = cleaned
    project.updated_at = datetime.now(UTC)
    await db.flush()
    return {
        "domain": cleaned,
        "record_type": "CNAME",
        "host": cleaned,
        "target": "cname.helm.app",
        "status": "pending_dns",
        "guidance": (
            f"Add a CNAME record on your DNS provider pointing {cleaned} "
            "to cname.helm.app. Automatic certificate issuance ships in a "
            "follow-up — for now reach out to support once the DNS "
            "propagates and we'll flip you live."
        ),
    }


async def load_published_files(
    db: AsyncSession, *, slug: str
) -> tuple[BuilderProject, dict[str, BuilderProjectFile]] | None:
    """Return the published project + its file rows by slug.

    Used by the public `/apps/{slug}` Next route (via a backend
    fetch) and by any direct API clients.
    """
    proj_q = await db.execute(
        select(BuilderProject).where(
            BuilderProject.slug == slug, BuilderProject.status == "published"
        )
    )
    project = proj_q.scalar_one_or_none()
    if project is None or project.current_version_id is None:
        return None
    fq = await db.execute(
        select(BuilderProjectFile).where(
            BuilderProjectFile.version_id == project.current_version_id
        )
    )
    files = {f.path: f for f in fq.scalars().all()}
    return project, files

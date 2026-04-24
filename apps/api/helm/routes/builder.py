"""Builder REST routes — founder-facing endpoints for the Builder
feature inside Helm.

    GET    /builder/projects                     — list
    POST   /builder/projects                     — create (blank | import_github | import_zip)
    GET    /builder/projects/{id}                — detail
    PATCH  /builder/projects/{id}                — rename / custom_domain edits
    DELETE /builder/projects/{id}                — archive

    GET    /builder/projects/{id}/files          — current-version file tree
    GET    /builder/projects/{id}/files/{path}   — single file content (future — preview uses manifest)
    GET    /builder/projects/{id}/preview_manifest — WebContainer-ready manifest

    POST   /builder/projects/{id}/plan           — propose a plan
    GET    /builder/projects/{id}/plans          — list plans
    GET    /builder/plans/{id}                   — plan detail
    POST   /builder/plans/{id}/approve           — approve + apply
    POST   /builder/plans/{id}/reject            — reject

    POST   /builder/projects/{id}/undo           — one-step undo

    GET    /builder/projects/{id}/versions       — version list
    GET    /builder/projects/{id}/verify         — re-run checks against current version
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import (
    BuilderPlan,
    BuilderProject,
    BuilderProjectFile,
    BuilderVersion,
)
from helm.db.session import get_session
from helm.errors import ClientError, upstream_unavailable
from helm.services.builder import (
    frameworks,
    github_client,
    orchestrator,
    publisher,
    templates,
    versioning,
)
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["builder"])


def _ensure_enabled() -> None:
    if not get_settings().builder_enabled:
        raise HTTPException(status_code=404, detail="builder not enabled")


# ──────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────


class BuilderProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    name: str
    slug: str
    description: str | None
    source_type: str
    source_url: str | None
    framework: str
    status: str
    github_repo_url: str | None
    published_url: str | None
    custom_domain: str | None
    current_version_id: uuid.UUID | None
    previous_version_id: uuid.UUID | None
    daily_spend_cents: int
    daily_spend_cap_cents: int
    created_at: datetime
    updated_at: datetime


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    source_type: str = Field(default="blank", pattern=r"^(blank|import_github|import_zip)$")
    source_url: str | None = Field(default=None, max_length=500)
    template: str = Field(default="vite_react")
    business_id: uuid.UUID | None = None


class PatchProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    custom_domain: str | None = Field(default=None, max_length=253)
    daily_spend_cap_cents: int | None = Field(default=None, ge=0, le=100000)


class ProjectFileResponse(BaseModel):
    path: str
    content: str
    hash: str
    binary_url: str | None


class PreviewManifestResponse(BaseModel):
    framework: str
    dev_command: list[str]
    files: dict[str, str]


class PlanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_prompt: str
    plain_plan: str
    technical_plan: str
    affected_areas: list[dict[str, Any]]
    risks: str | None
    recommendation: str | None
    file_hints: list[str]
    model_used: str | None
    status: str
    applied_version_id: uuid.UUID | None
    error: str | None
    created_at: datetime


class ProposePlanRequest(BaseModel):
    user_prompt: str = Field(min_length=1, max_length=4000)


class VersionResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_version_id: uuid.UUID | None
    label: str | None
    change_summary_plain: str | None
    change_summary_technical: str | None
    commit_sha: str | None
    created_at: datetime


class VerifyResponse(BaseModel):
    ok: bool
    checks: list[dict[str, Any]]
    warnings: int
    errors: int


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


async def _project_for_user(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> BuilderProject:
    row = await db.get(BuilderProject, project_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="project not found")
    return row


# ──────────────────────────────────────────────────────────
# Projects
# ──────────────────────────────────────────────────────────


@router.get("/builder/projects", response_model=list[BuilderProjectResponse])
async def list_projects(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[BuilderProjectResponse]:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    q = await db.execute(
        select(BuilderProject)
        .where(BuilderProject.user_id == user_row.id)
        .order_by(desc(BuilderProject.updated_at))
    )
    return [
        BuilderProjectResponse.model_validate(r, from_attributes=True)
        for r in q.scalars().all()
    ]


@router.post(
    "/builder/projects", response_model=BuilderProjectResponse, status_code=201
)
async def create_project(
    body: CreateProjectRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BuilderProjectResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)

    base_slug = _slugify(body.name)
    # Ensure unique slug for this user.
    slug = base_slug
    exists_q = await db.execute(
        select(BuilderProject.slug).where(
            BuilderProject.user_id == user_row.id, BuilderProject.slug.like(f"{base_slug}%")
        )
    )
    taken = {r[0] for r in exists_q.all()}
    n = 1
    while slug in taken:
        n += 1
        slug = f"{base_slug}-{n}"

    # Seed files.
    if body.source_type == "blank":
        seed = templates.get(body.template)
        framework_info = frameworks.detect(seed)
    elif body.source_type == "import_github":
        if not body.source_url:
            raise HTTPException(
                status_code=400,
                detail="Paste a public GitHub repo URL to import.",
            )
        try:
            ref = github_client.parse_repo_url(body.source_url)
            seed = await github_client.fetch_public_repo_files(
                owner=ref["owner"], repo=ref["repo"], ref=ref["ref"]
            )
        except github_client.GitHubImportError as e:
            raise ClientError(
                "github_import_failed",
                status_code=400,
                message=str(e),
            ) from e
        framework_info = frameworks.detect(seed)
    elif body.source_type == "import_zip":
        # ZIP bytes arrive on a separate endpoint; this path only fires
        # when the client created a shell project via legacy wizard.
        # Seed with a helpful placeholder and let the user re-create
        # via /builder/import/zip if they prefer.
        seed = {
            "index.html": (
                "<!doctype html><html><body><main>"
                "<h1>Upload a ZIP</h1>"
                "<p>Create your project via the ZIP import endpoint to "
                "populate real files.</p></main></body></html>\n"
            ),
        }
        framework_info = frameworks.info("static")
    else:
        raise HTTPException(status_code=400, detail="unknown source_type")

    project = BuilderProject(
        user_id=user_row.id,
        business_id=body.business_id,
        name=body.name.strip(),
        slug=slug,
        description=body.description,
        source_type=body.source_type,
        source_url=body.source_url,
        framework=framework_info["framework"],
        status="draft",
    )
    db.add(project)
    await db.flush()

    await versioning.write_initial(
        db, project_id=project.id, files=seed, label="initial"
    )
    await db.commit()
    await db.refresh(project)
    return BuilderProjectResponse.model_validate(project, from_attributes=True)


@router.get(
    "/builder/projects/{project_id}", response_model=BuilderProjectResponse
)
async def get_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BuilderProjectResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    row = await _project_for_user(db, user_row.id, project_id)
    return BuilderProjectResponse.model_validate(row, from_attributes=True)


@router.patch(
    "/builder/projects/{project_id}", response_model=BuilderProjectResponse
)
async def patch_project(
    project_id: uuid.UUID,
    body: PatchProjectRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BuilderProjectResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    row = await _project_for_user(db, user_row.id, project_id)
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description
    if body.custom_domain is not None:
        row.custom_domain = body.custom_domain.strip() or None
    if body.daily_spend_cap_cents is not None:
        row.daily_spend_cap_cents = body.daily_spend_cap_cents
    await db.commit()
    await db.refresh(row)
    return BuilderProjectResponse.model_validate(row, from_attributes=True)


@router.delete("/builder/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    row = await _project_for_user(db, user_row.id, project_id)
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────
# Files + preview manifest
# ──────────────────────────────────────────────────────────


@router.get(
    "/builder/projects/{project_id}/files",
    response_model=list[ProjectFileResponse],
)
async def list_files(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ProjectFileResponse]:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    proj = await _project_for_user(db, user_row.id, project_id)
    if proj.current_version_id is None:
        return []
    q = await db.execute(
        select(BuilderProjectFile)
        .where(BuilderProjectFile.version_id == proj.current_version_id)
        .order_by(BuilderProjectFile.path.asc())
    )
    return [
        ProjectFileResponse(
            path=f.path, content=f.content, hash=f.hash, binary_url=f.binary_url
        )
        for f in q.scalars().all()
    ]


@router.get(
    "/builder/projects/{project_id}/preview_manifest",
    response_model=PreviewManifestResponse,
)
async def preview_manifest(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PreviewManifestResponse:
    """Return a WebContainer-ready file tree and the framework's dev command.

    The browser (PreviewFrame) mounts `files`, runs `npm install`, then
    spawns `dev_command`."""
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    proj = await _project_for_user(db, user_row.id, project_id)
    if proj.current_version_id is None:
        raise HTTPException(status_code=409, detail="project has no current version")
    q = await db.execute(
        select(BuilderProjectFile).where(
            BuilderProjectFile.version_id == proj.current_version_id
        )
    )
    files = {f.path: f.content for f in q.scalars().all()}
    info = frameworks.info(proj.framework)  # type: ignore[arg-type]
    return PreviewManifestResponse(
        framework=info["framework"],
        dev_command=list(info["dev_command"]),
        files=files,
    )


# ──────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────


@router.post(
    "/builder/projects/{project_id}/plan",
    response_model=PlanResponse,
    status_code=201,
)
async def propose_plan(
    project_id: uuid.UUID,
    body: ProposePlanRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PlanResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    try:
        plan_row = await orchestrator.propose_plan(
            db,
            project_id=project_id,
            user_id=user_row.id,
            user_prompt=body.user_prompt,
        )
    except orchestrator.DailySpendCapError as e:
        raise ClientError(
            "daily_spend_cap_reached",
            status_code=402,
            message=(
                "You've hit today's Builder spend cap. It resets at midnight "
                "UTC, or raise the cap in Settings → Billing."
            ),
        ) from e
    except orchestrator.BuilderError as e:
        raise ClientError(
            "builder_plan_failed",
            status_code=400,
            message=str(e),
        ) from e
    await db.commit()
    await db.refresh(plan_row)
    return PlanResponse.model_validate(plan_row, from_attributes=True)


@router.get(
    "/builder/projects/{project_id}/plans",
    response_model=list[PlanResponse],
)
async def list_plans(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[PlanResponse]:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    q = await db.execute(
        select(BuilderPlan)
        .where(BuilderPlan.project_id == project_id)
        .order_by(desc(BuilderPlan.created_at))
    )
    return [
        PlanResponse.model_validate(p, from_attributes=True)
        for p in q.scalars().all()
    ]


@router.get("/builder/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PlanResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    plan_row = await db.get(BuilderPlan, plan_id)
    if plan_row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _project_for_user(db, user_row.id, plan_row.project_id)
    return PlanResponse.model_validate(plan_row, from_attributes=True)


@router.post("/builder/plans/{plan_id}/approve", response_model=PlanResponse)
async def approve_plan(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PlanResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    plan_row = await db.get(BuilderPlan, plan_id)
    if plan_row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _project_for_user(db, user_row.id, plan_row.project_id)
    try:
        await orchestrator.apply_plan(db, plan_id=plan_id, user_id=user_row.id)
    except orchestrator.DailySpendCapError as e:
        raise ClientError(
            "daily_spend_cap_reached",
            status_code=402,
            message=(
                "You've hit today's Builder spend cap. It resets at midnight "
                "UTC, or raise the cap in Settings → Billing."
            ),
        ) from e
    except orchestrator.BuilderError as e:
        raise upstream_unavailable("The Builder service") from e
    await db.commit()
    await db.refresh(plan_row)
    return PlanResponse.model_validate(plan_row, from_attributes=True)


@router.post("/builder/plans/{plan_id}/reject", response_model=PlanResponse)
async def reject_plan(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PlanResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    plan_row = await db.get(BuilderPlan, plan_id)
    if plan_row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _project_for_user(db, user_row.id, plan_row.project_id)
    plan_row.status = "rejected"
    await db.commit()
    await db.refresh(plan_row)
    return PlanResponse.model_validate(plan_row, from_attributes=True)


# ──────────────────────────────────────────────────────────
# Undo + versions + verify
# ──────────────────────────────────────────────────────────


@router.post(
    "/builder/projects/{project_id}/undo", response_model=VersionResponse | None
)
async def undo(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> VersionResponse | None:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    prev = await versioning.undo_last(db, project_id=project_id)
    await db.commit()
    if prev is None:
        return None
    return VersionResponse.model_validate(prev, from_attributes=True)


@router.get(
    "/builder/projects/{project_id}/versions",
    response_model=list[VersionResponse],
)
async def list_versions(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[VersionResponse]:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    q = await db.execute(
        select(BuilderVersion)
        .where(BuilderVersion.project_id == project_id)
        .order_by(desc(BuilderVersion.created_at))
        .limit(100)
    )
    return [
        VersionResponse.model_validate(v, from_attributes=True)
        for v in q.scalars().all()
    ]


@router.get(
    "/builder/projects/{project_id}/verify", response_model=VerifyResponse
)
async def verify_current(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> VerifyResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    report = await orchestrator.verify_report_for(db, project_id=project_id)
    return VerifyResponse(**report)


# ──────────────────────────────────────────────────────────
# Publish (helm-hosted + custom domain stub)
# ──────────────────────────────────────────────────────────


class PublishResponse(BaseModel):
    project_id: uuid.UUID
    slug: str
    published_url: str | None
    status: str


class CustomDomainRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=253)


class CustomDomainResponse(BaseModel):
    domain: str
    record_type: str
    host: str
    target: str
    status: str
    guidance: str


@router.post(
    "/builder/projects/{project_id}/publish", response_model=PublishResponse
)
async def publish_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PublishResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    try:
        project = await publisher.publish_helm_hosted(db, project_id=project_id)
    except publisher.PublishError as e:
        raise ClientError(
            "publish_failed",
            status_code=400,
            message=str(e),
        ) from e
    await db.commit()
    await db.refresh(project)
    return PublishResponse(
        project_id=project.id,
        slug=project.slug,
        published_url=project.published_url,
        status=project.status,
    )


@router.post(
    "/builder/projects/{project_id}/custom_domain",
    response_model=CustomDomainResponse,
)
async def set_custom_domain(
    project_id: uuid.UUID,
    body: CustomDomainRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> CustomDomainResponse:
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    try:
        payload = await publisher.request_custom_domain(
            db, project_id=project_id, domain=body.domain
        )
    except publisher.PublishError as e:
        raise ClientError(
            "custom_domain_failed",
            status_code=400,
            message=str(e),
        ) from e
    await db.commit()
    return CustomDomainResponse(**payload)


# ──────────────────────────────────────────────────────────
# Public app serving — no auth; served at /apps/{slug}
# ──────────────────────────────────────────────────────────

_public_router = APIRouter(tags=["builder_public"])


def _guess_content_type(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "html": "text/html; charset=utf-8",
        "htm": "text/html; charset=utf-8",
        "css": "text/css; charset=utf-8",
        "js": "application/javascript; charset=utf-8",
        "mjs": "application/javascript; charset=utf-8",
        "json": "application/json; charset=utf-8",
        "svg": "image/svg+xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "ico": "image/x-icon",
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
        "woff": "font/woff",
        "woff2": "font/woff2",
        "ttf": "font/ttf",
    }.get(ext, "application/octet-stream")


@_public_router.get("/apps/{slug}")
@_public_router.get("/apps/{slug}/")
async def serve_published_root(
    slug: str, db: AsyncSession = Depends(get_session)
) -> Response:
    return await _serve_public(db, slug=slug, path="index.html")


@_public_router.get("/apps/{slug}/{path:path}")
async def serve_published_asset(
    slug: str, path: str, db: AsyncSession = Depends(get_session)
) -> Response:
    return await _serve_public(db, slug=slug, path=path)


async def _serve_public(db: AsyncSession, *, slug: str, path: str) -> Response:
    loaded = await publisher.load_published_files(db, slug=slug)
    if loaded is None:
        return Response(
            content=(
                "<!doctype html><title>Not found</title>"
                "<p>This project isn't published yet.</p>"
            ),
            media_type="text/html; charset=utf-8",
            status_code=404,
        )
    _, files = loaded
    # Normalize requested path: default to index.html at any directory.
    want = path.lstrip("/")
    if not want or want.endswith("/"):
        want = want + "index.html"
    row = files.get(want) or files.get(f"{want}/index.html")
    if row is None:
        # Fall back to index.html so client-side routing works.
        row = files.get("index.html") or files.get("public/index.html")
        if row is None:
            return Response(
                content="<p>Not found.</p>",
                media_type="text/html; charset=utf-8",
                status_code=404,
            )
    return Response(
        content=row.content,
        media_type=_guess_content_type(row.path),
        status_code=200,
    )


# Exposed for main.py to register alongside the authed router.
public_router = _public_router


# ──────────────────────────────────────────────────────────
# Import / Export
# ──────────────────────────────────────────────────────────

from fastapi import File, Form, UploadFile  # noqa: E402


@router.post(
    "/builder/import/zip",
    response_model=BuilderProjectResponse,
    status_code=201,
)
async def import_zip(
    name: str = Form(...),
    description: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BuilderProjectResponse:
    """Create a project from an uploaded ZIP. We read the ZIP, drop
    binaries + node_modules/.git, keep text files up to the per-file
    and total budget."""
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > 40_000_000:
        raise HTTPException(status_code=413, detail="ZIP too large (max 40MB)")

    try:
        files_map = github_client.unpack_zip(data)
    except github_client.GitHubImportError as e:
        raise ClientError(
            "zip_import_failed",
            status_code=400,
            message=str(e),
        ) from e

    base_slug = _slugify(name)
    exists_q = await db.execute(
        select(BuilderProject.slug).where(
            BuilderProject.user_id == user_row.id,
            BuilderProject.slug.like(f"{base_slug}%"),
        )
    )
    taken = {r[0] for r in exists_q.all()}
    slug = base_slug
    n = 1
    while slug in taken:
        n += 1
        slug = f"{base_slug}-{n}"

    framework_info = frameworks.detect(files_map)
    project = BuilderProject(
        user_id=user_row.id,
        name=name.strip(),
        slug=slug,
        description=description,
        source_type="import_zip",
        source_url=file.filename,
        framework=framework_info["framework"],
        status="draft",
    )
    db.add(project)
    await db.flush()
    await versioning.write_initial(
        db, project_id=project.id, files=files_map, label="initial"
    )
    await db.commit()
    await db.refresh(project)
    return BuilderProjectResponse.model_validate(project, from_attributes=True)


@router.get("/builder/projects/{project_id}/export/zip")
async def export_zip(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Download the project's current file tree as a ZIP."""
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    project = await _project_for_user(db, user_row.id, project_id)
    if project.current_version_id is None:
        raise HTTPException(status_code=409, detail="project has no files")
    fq = await db.execute(
        select(BuilderProjectFile).where(
            BuilderProjectFile.version_id == project.current_version_id
        )
    )
    files_map = {f.path: f.content for f in fq.scalars().all()}
    data = github_client.build_export_zip(files_map)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{project.slug}.zip"'
        },
    )


class GitHubPushResponse(BaseModel):
    status: str
    message: str


@router.post(
    "/builder/projects/{project_id}/export/github",
    response_model=GitHubPushResponse,
    status_code=202,
)
async def export_github(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> GitHubPushResponse:
    """Stub: GitHub push needs the user's OAuth connection, which rolls
    out alongside Composio GitHub connector. For now we return 202 with
    a plain-English next step."""
    _ensure_enabled()
    user_row = await sync_user_from_supabase(db, user)
    await _project_for_user(db, user_row.id, project_id)
    return GitHubPushResponse(
        status="pending_connection",
        message=(
            "Connect GitHub under Connections to push from Builder. "
            "You can export a ZIP today — Builder will commit directly "
            "once the GitHub connection is live."
        ),
    )

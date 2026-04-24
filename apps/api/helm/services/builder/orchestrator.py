"""Builder orchestrator — glues intent/plan/execute/verify/explain/
versioning into `propose_plan` and `apply_plan`.

Every layer is LLM-backed (or static) via a small helper in `_llm.py`.
The shape is: read current state → reserve credits + call LLM → write
back. Failures roll back to the pre-snapshot version.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import (
    BuilderPlan,
    BuilderProject,
    BuilderProjectFile,
    BuilderVersion,
)
from helm.services.builder import (
    _llm,
    execute,
    explain,
    intent,
    plan,
    verify,
    versioning,
)

log = structlog.get_logger("helm.builder.orchestrator")


class BuilderError(Exception):
    """Any orchestrator-level failure. Routes convert to 4xx/5xx."""


class DailySpendCapError(BuilderError):
    """Project hit its daily LLM-spend cap."""


async def propose_plan(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    user_prompt: str,
) -> BuilderPlan:
    """Parse intent, generate a Plan, persist it. Returns the Plan row."""
    project = await _load_project(db, project_id)
    if project.user_id != user_id:
        raise BuilderError("not your project")

    parsed_intent = await intent.parse(
        db,
        project_id=project_id,
        user_id=user_id,
        user_prompt=user_prompt,
        project_name=project.name,
    )

    # File tree paths — not contents — for the planner.
    file_paths: list[str] = []
    if project.current_version_id is not None:
        q = await db.execute(
            select(BuilderProjectFile.path).where(
                BuilderProjectFile.version_id == project.current_version_id
            )
        )
        file_paths = [row[0] for row in q.all()]

    generated = await plan.generate(
        db,
        project_id=project_id,
        user_id=user_id,
        intent=parsed_intent,
        project_name=project.name,
        user_prompt=user_prompt,
        file_tree=file_paths,
    )

    row = BuilderPlan(
        project_id=project_id,
        user_prompt=user_prompt,
        plain_plan=generated["plain_plan"],
        technical_plan=generated["technical_plan"],
        affected_areas=list(generated["affected_areas"]),
        risks=generated["risks"],
        recommendation=generated["recommendation"],
        file_hints=list(generated["file_hints"]),
        model_used=generated["model_used"],
        status="proposed",
    )
    db.add(row)
    await db.flush()
    log.info(
        "builder.plan.proposed",
        project_id=str(project_id),
        plan_id=str(row.id),
        model=generated["model_used"],
    )
    return row


async def apply_plan(
    db: AsyncSession,
    *,
    plan_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BuilderVersion:
    """Apply an approved plan. Wraps the execute call in a snapshot +
    verify + explain sequence. On failure we mark plan failed and leave
    the pre-snapshot state intact (one-step undo is already available).
    """
    plan_row = await db.get(BuilderPlan, plan_id)
    if plan_row is None:
        raise BuilderError("plan not found")
    if plan_row.status not in ("proposed", "approved"):
        raise BuilderError(f"plan is {plan_row.status} — can't apply")

    project_id = plan_row.project_id
    project = await _load_project(db, project_id)
    if project.user_id != user_id:
        raise BuilderError("not your project")

    if project.daily_spend_cents >= project.daily_spend_cap_cents:
        raise DailySpendCapError(
            f"daily spend cap hit ({project.daily_spend_cap_cents}c)"
        )

    # Load current files.
    current_files: dict[str, str] = {}
    if project.current_version_id is not None:
        fq = await db.execute(
            select(BuilderProjectFile).where(
                BuilderProjectFile.version_id == project.current_version_id
            )
        )
        for f in fq.scalars().all():
            current_files[f.path] = f.content

    # 1. Snapshot pre-state.
    new_version = await versioning.snapshot(
        db, project_id=project_id, label=f"plan:{plan_row.id}"
    )

    # 2. Execute — LLM returns file ops.
    try:
        result = await execute.apply(
            db,
            project_id=project_id,
            plan_id=plan_id,
            user_id=user_id,
            plain_plan=plan_row.plain_plan,
            technical_plan=plan_row.technical_plan,
            file_hints=list(plan_row.file_hints),
            files=current_files,
        )
    except DailySpendCapError:
        raise
    except _llm.BuilderLLMError as e:
        log.exception("builder.apply.execute_failed", plan_id=str(plan_id))
        plan_row.status = "failed"
        plan_row.error = str(e)[:300]
        await db.flush()
        raise BuilderError(f"execute failed: {e}") from e

    # 3. Map ops onto writes/deletes.
    writes: dict[str, str] = {}
    deletes: list[str] = []
    for op in result["ops"]:
        if op.get("op") == "write":
            writes[op["path"]] = op.get("content", "")
        elif op.get("op") == "delete":
            deletes.append(op["path"])

    # 4. Build post-state view for verify.
    post_files = dict(current_files)
    for p, c in writes.items():
        post_files[p] = c
    for p in deletes:
        post_files.pop(p, None)

    await versioning.commit_changes(
        db,
        project_id=project_id,
        new_version_id=new_version.id,
        writes=writes,
        deletes=deletes,
    )

    # 5. Verify touched files.
    touched = list(writes.keys())
    verify_report = await verify.run(files=post_files, touched_paths=touched)

    # 6. Finalize pointer.
    await versioning.finalize(
        db, project_id=project_id, new_version_id=new_version.id
    )

    # 7. Explain (LLM; failure is non-fatal).
    summary = await explain.summarize(
        db,
        project_id=project_id,
        plan_id=plan_id,
        user_id=user_id,
        plain_plan=plan_row.plain_plan,
        touched_paths=touched,
        verify=verify_report,
    )
    new_version.change_summary_plain = summary
    new_version.change_summary_technical = result["logs"]

    plan_row.status = "applied"
    plan_row.applied_version_id = new_version.id
    await db.flush()

    log.info(
        "builder.apply.completed",
        project_id=str(project_id),
        plan_id=str(plan_id),
        version=str(new_version.id),
        touched=len(touched),
        verify_ok=verify_report["ok"],
    )
    return new_version


async def _load_project(db: AsyncSession, project_id: uuid.UUID) -> BuilderProject:
    proj = await db.get(BuilderProject, project_id)
    if proj is None:
        raise BuilderError("project not found")
    return proj


async def verify_report_for(
    db: AsyncSession, *, project_id: uuid.UUID
) -> dict[str, object]:
    project = await _load_project(db, project_id)
    if project.current_version_id is None:
        return {"ok": True, "checks": [], "warnings": 0, "errors": 0}
    fq = await db.execute(
        select(BuilderProjectFile).where(
            BuilderProjectFile.version_id == project.current_version_id
        )
    )
    files = {f.path: f.content for f in fq.scalars().all()}
    return dict(await verify.run(files=files, touched_paths=list(files.keys())))

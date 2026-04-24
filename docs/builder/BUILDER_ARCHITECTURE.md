# Builder — Architecture

Supplemental to `SPEC.md`. This doc details module boundaries, data flow, LLM
prompts, preview-runtime integration, and reuse-vs-new decisions.

## 1. Module map

```
apps/api/helm/services/builder/
  __init__.py
  intent.py                    # parse founder prompt → structured Intent
  plan.py                      # intent + project context → Plan
  execute.py                   # approved Plan → project-file writes
  verify.py                    # syntax + lint + tsc, plain-English report
  explain.py                   # user-facing diff summary
  versioning.py                # snapshot, load, one-step undo
  orchestrator.py              # glue all layers into propose_plan / apply_plan
  preview.py                   # WebContainer manifest + short-lived token
  publisher.py                 # helm-hosted + custom-domain deploy
  github_client.py             # clone / push via OAuth
  frameworks.py                # detect framework, pick scaffolds
  templates/                   # blank starter templates per framework
    blank_vite_react/
    blank_next/
    blank_static/

apps/api/helm/routes/
  builder.py                   # all /builder/* REST endpoints
  builder_webhooks.py          # deployment callbacks (if needed)

apps/web/app/builder/
  layout.tsx                   # builder shell (sidebar-free; full-screen workspace)
  page.tsx                     # project list
  new/page.tsx                 # creation wizard
  [id]/page.tsx                # workspace (chat + preview + drawer)
  [id]/publish/page.tsx        # publish panel

apps/web/components/builder/
  ProjectCard.tsx
  ChatPane.tsx                 # Ask / Plan / Review chat UI
  PlanReview.tsx               # plain + technical plan with approve/reject
  VerifyReport.tsx             # plain-English check results
  PreviewFrame.tsx             # WebContainer-hosted iframe
  FileDrawer.tsx               # file tree (hidden by default)
  PublishPanel.tsx
  UndoButton.tsx
```

## 2. Six-layer contract

Each layer is **pure**: takes structured input, returns structured output, side
effects contained. This makes the orchestrator testable and each layer
independently replaceable.

```python
# intent.py
async def parse(*, user_prompt: str, project: Project) -> Intent: ...

class Intent(TypedDict):
    kind: Literal["create","edit","import","publish","undo","refine"]
    summary: str            # one-line restatement
    targets: list[str]      # e.g. ["pages","pricing","components/Hero.tsx"]
    needs_planning: bool    # false for simple single-file edits

# plan.py
async def generate(*, intent: Intent, project: Project, files: list[File]) -> Plan: ...

class Plan(TypedDict):
    plain_plan: str
    technical_plan: str
    affected_areas: list[dict]   # [{label, rationale}]
    risks: str
    recommendation: str
    file_hints: list[str]        # paths the model expects to write
    model_used: str

# execute.py
async def apply(*, plan: Plan, project: Project, files: list[File]) -> ExecuteResult: ...

class ExecuteResult(TypedDict):
    written_files: list[WrittenFile]     # [{path, old_hash, new_hash, content}]
    deleted_paths: list[str]
    logs: str                            # for debugging / technical view

# verify.py
async def run(*, project: Project, touched_paths: list[str]) -> VerifyReport: ...

class VerifyReport(TypedDict):
    ok: bool
    checks: list[dict]          # [{name, status, plain_english, detail?}]
    warnings: int
    errors: int

# explain.py
async def summarize(*, plan: Plan, result: ExecuteResult, verify: VerifyReport) -> str: ...
# returns a founder-facing paragraph ("Updated your hero headline and bumped
# the accent color to warm terracotta. One warning: the OG image is still
# pointing at the old color — want me to fix that?")

# versioning.py
async def snapshot(project_id) -> Version: ...
async def undo_last(project_id) -> Version: ...
async def load_current(project_id) -> list[File]: ...
```

## 3. Orchestrator

```python
# orchestrator.py
async def propose_plan(db, project_id, user_prompt) -> Plan:
    proj = await load_project(db, project_id)
    files = await load_files(db, project_id)
    intent = await intent.parse(user_prompt=user_prompt, project=proj)
    plan = await plan.generate(intent=intent, project=proj, files=files)
    return await persist_plan(db, project_id, plan, intent)

async def apply_plan(db, plan_id) -> Version:
    plan = await load_plan(db, plan_id)
    project_id = plan.project_id
    # 1. Snapshot current state — sets previous_version_id for one-step undo
    pre = await versioning.snapshot(project_id)
    # 2. Execute
    result = await execute.apply(plan=plan, project=proj, files=files)
    # 3. New version row
    new_version = await versioning.commit(project_id, parent=pre.id, result=result)
    # 4. Verify touched files
    verify_report = await verify.run(project=proj, touched_paths=[f.path for f in result.written_files])
    # 5. Explain
    summary = await explain.summarize(plan=plan, result=result, verify=verify_report)
    # 6. Update plan row + emit analytics
    await mark_applied(db, plan_id, new_version.id, summary, verify_report)
    return new_version
```

## 4. Reuse vs new work

| Concern | Reuse | New |
|---|---|---|
| Auth | `auth.CurrentUser`, Supabase JWT | — |
| Credits | `services/credits.py` | — |
| LLM integration | `anthropic.AsyncAnthropic` (already in deps) | `builder/prompts.py` (prompt pack per layer) |
| OAuth (GitHub) | `integration_vault`, Composio adapter pattern | `builder/github_client.py` thin wrapper |
| Design system | `components/ui/*`, paper/ink palette | `components/builder/*` feature-specific |
| Nav shell | `AppShell.tsx` | top-level `/builder` entry |
| Analytics | existing `event_log.py` | new event_type values |
| Background jobs | existing scheduler.py | new `builder_verify` tick for async deep verification (post-v1) |
| Migrations | alembic | `019_builder.py` |
| Storage (binary files) | Supabase Storage via existing client | `builder` bucket |

No new frameworks, no new auth, no new deployment platform. Builder runs on the
same FastAPI + Next.js + Supabase stack.

## 5. LLM prompt pack

`services/builder/prompts.py` — one prompt per layer, not one giant prompt.

### Intent prompt (Haiku 4.5)

```
System:
You categorize a founder's Builder request into a structured intent.
The founder is non-technical. Keep `summary` in plain English.

Output JSON: {kind, summary, targets[], needs_planning}

Rules:
- kind ∈ {create, edit, import, publish, undo, refine}
- targets: the pages/features/files the request most plausibly touches
- needs_planning=false only for trivial one-file cosmetic tweaks
```

### Plan prompt (Sonnet 4.6 default; Opus 4.7 when project >20 files)

```
System:
You are Builder's planner. Given a Helm founder's request and their
current project file tree, propose a change plan.

Output JSON: {plain_plan, technical_plan, affected_areas[], risks,
              recommendation, file_hints[]}

plain_plan MUST be:
- written to a non-technical founder
- 2-4 short sentences
- reference pages/features/data/design, NEVER repos/branches/commits

technical_plan is for a collapsed "advanced" pane — fuller detail.

affected_areas: a list of {label, rationale} where `label` is
founder-language ("Pricing page", "Hero section", "Checkout flow").
```

### Execute prompt (Sonnet 4.6)

```
System:
You are Builder's executor. Apply the approved plan. Output a JSON array
of file operations:

[{op: "write", path, content}, {op: "delete", path}]

Rules:
- Do not rewrite files unrelated to the plan
- Match the project's existing framework and style
- Keep imports stable; reuse existing utilities
- No TODO comments; ship working code
```

### Verify prompt (not LLM — actual tools)

- TS project: run `tsc --noEmit` in the WebContainer (client-side) or run a
  server-side `esbuild --bundle --check` on touched files (cheap fallback).
- Add `eslint` if present in `package.json`.
- For non-TS (static HTML/CSS): run an HTML validator (`htmlhint`) and
  CSS parser.
- Map errors/warnings → founder English via Haiku 4.5.

### Explain prompt (Haiku 4.5)

```
System:
Summarize the applied change to a founder in one paragraph.
Reference pages/sections by their visible name. Avoid jargon.
If verify failed or warned, include what it means and what to try next.
```

## 6. Preview runtime deep-dive

StackBlitz `@webcontainer/api` runs Node in the browser via WebAssembly. Zero
server cost, fast boot, but needs cross-origin-isolation headers on the
/builder route.

```ts
// web: apps/web/components/builder/PreviewFrame.tsx
import { WebContainer } from "@webcontainer/api";

async function boot(manifest: FileManifest) {
  const wc = await WebContainer.boot();
  await wc.mount(manifestToFileTree(manifest));
  const install = await wc.spawn("npm", ["install"]);
  await install.exit;
  const dev = await wc.spawn("npm", ["run", "dev"]);
  wc.on("server-ready", (port, url) => {
    setIframeUrl(url);
  });
}
```

Backend supplies the manifest via `GET /builder/{id}/preview_manifest` — a
JSON blob `{ path -> content }`. For large projects (>2MB), we stream file
entries and the client hydrates incrementally.

Next.js config:

```ts
// next.config.mjs — scoped header for /builder
{
  async headers() {
    return [{
      source: "/builder/:path*",
      headers: [
        { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      ],
    }];
  }
}
```

## 7. GitHub integration

1. User connects GitHub via `/connections/account` using the existing Composio
   flow (we add `github` to the catalog).
2. On **Import**, Builder POSTs `{ repo_url }` → backend fetches the repo
   tarball via `GET /repos/{owner}/{repo}/tarball/{ref}`, unpacks, stores
   files in `builder_project_files` as the initial version.
3. On **Push**, Builder walks `current_version.manifest` minus the last
   pushed `commit_sha`, commits each file via `PUT /repos/{owner}/{repo}/contents/{path}`.
   For performance we eventually move to the Git Data API (blobs → tree →
   commit → ref) but the simple Contents API is enough for v1.

## 8. Publisher

```
publisher.publish_helm_hosted(project_id):
  1. Run `npm run build` inside a server-side WebContainer or a lightweight
     Node buildpack. For v1 we accept only static-outputable frameworks
     (Vite, Next static export, pure static).
  2. Upload `dist/` to Supabase Storage under `builder-public/<slug>/`
  3. Update `projects.published_url = "https://helm.app/apps/<slug>"`
  4. Serve via a new Next.js route that reads from Supabase Storage

publisher.publish_custom_domain(project_id, domain):
  1. Store `custom_domain`
  2. Return CNAME instructions page — show target `cname.helm.app`
  3. (v2) Poll DNS; once resolved, run acme to issue a Let's Encrypt cert;
     store cert in Supabase; ingress gateway serves
```

## 9. One-step undo

Simplest safe model:

```
Before each execute.apply:
    pre = versioning.snapshot(project_id)        # writes builder_versions row
                                                  # with full manifest
After:
    project.previous_version_id = pre.id

Undo button:
    versioning.undo_last(project_id):
        prev = load version(project.previous_version_id)
        for path, hash in prev.snapshot_manifest:
            restore file row
        project.current_version_id = prev.id
        project.previous_version_id = prev.parent_version_id or null
```

The only state mutated is the project file set — preview re-boots to reflect.
Analytics events fired so we can quantify how often undo is used.

## 10. Cost control

- Per-project `daily_spend_cap_cents` (default 500 = $5, configurable per-tier).
- Every LLM call goes through `credits.reserve/commit` AND increments
  `builder_projects.daily_spend_cents` inside the same transaction.
- On day rollover (UTC midnight) a light job resets `daily_spend_cents`.
- Soft warning UI at 60%, hard block at 100% with top-up CTA.

## 11. What we explicitly DO NOT do in v1

- Run user server code on Helm's infra. Preview = browser WebContainer only.
- Stream partial file edits — apply_plan is transactional (snapshot → all-or-nothing write).
- Multi-project shared components library. Each project is isolated.
- Auto-translate founder prompts across languages. English only.
- Complex multi-repo monorepo imports. Import = one repo / one ZIP.

## 12. Observability

Every LLM call writes a `builder_runs` row (step + model + tokens + cost) —
same shape as `agent_events` so the existing /events feed can optionally
include Builder activity.

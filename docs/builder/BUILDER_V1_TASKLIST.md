# Builder V1 — Task List

File-level task list for implementing Builder. Phases B0–B4 ship as V1; B5–B6
land as fast-follow. Each phase ends in a lint/type/smoke verification block.

## Phase B0 — Foundation

Goal: data model + service skeletons + route stubs + nav entry, no real LLM
yet. A shell the founder can navigate into and see "coming soon" states.

### Backend

- [ ] `alembic/versions/019_builder.py` — migration for:
  - `builder_projects`
  - `builder_project_files`
  - `builder_versions`
  - `builder_plans`
  - `builder_runs`
- [ ] `helm/db/models.py` — append 5 ORM classes
- [ ] `helm/services/builder/__init__.py` — package init
- [ ] `helm/services/builder/orchestrator.py` — stub functions with typed signatures
- [ ] `helm/services/builder/versioning.py` — snapshot/load/undo (real impl, no LLM)
- [ ] `helm/services/builder/frameworks.py` — framework detection heuristics
- [ ] `helm/routes/builder.py` — CRUD for projects + files + plans + versions
- [ ] `helm/main.py` — register `builder` router
- [ ] `helm/config.py` — add `HELM_BUILDER_ENABLED` (default true locally)

### Frontend

- [ ] `apps/web/lib/api.ts` — add Builder client types + functions
- [ ] `apps/web/app/builder/layout.tsx` — full-screen workspace shell (no sidebar; nav through AppShell's topbar)
- [ ] `apps/web/app/builder/page.tsx` — project list
- [ ] `apps/web/app/builder/new/page.tsx` — creation wizard (blank vs import)
- [ ] `apps/web/app/builder/[id]/page.tsx` — workspace placeholder
- [ ] `apps/web/components/AppShell.tsx` — add "Builder" nav entry (gated on `HELM_BUILDER_ENABLED`)

### Verify

```
ruff check + mypy --strict on new Python files
tsc --noEmit on web
alembic upgrade head
curl /openapi.json | grep builder  # confirms routes registered
```

---

## Phase B1 — Plan flow

Goal: founder can type a description, see a plan, approve or reject. No execution yet.

### Backend

- [ ] `helm/services/builder/prompts.py` — four prompts (intent, plan, execute, explain)
- [ ] `helm/services/builder/intent.py` — Claude Haiku call → typed `Intent`
- [ ] `helm/services/builder/plan.py` — Claude Sonnet (Opus if >20 files) → typed `Plan`
- [ ] `helm/services/builder/orchestrator.py` — real `propose_plan` (no apply yet)
- [ ] `helm/routes/builder.py` — `POST /builder/{id}/plan`, `GET /builder/plans/{id}`, `POST /builder/plans/{id}/{approve|reject}`
- [ ] Credit reserve/commit wired to each LLM call

### Frontend

- [ ] `apps/web/components/builder/ChatPane.tsx` — prompt box + turn list
- [ ] `apps/web/components/builder/PlanReview.tsx` — plain plan + expand for technical + affected areas + risks + Approve/Reject
- [ ] `apps/web/app/builder/[id]/page.tsx` — chat pane wired to `POST /builder/{id}/plan`
- [ ] Founder-language check: no "migration", "commit", "branch" anywhere user-facing

### Verify

```
Backend lint + type
Web tsc
Smoke: create project; ask "Add a hero"; plan appears; reject works
```

---

## Phase B2 — Execute + verify

Goal: approving a plan writes files and reports what happened in plain English.

### Backend

- [ ] `helm/services/builder/execute.py` — Claude Sonnet with file-op JSON output
- [ ] `helm/services/builder/verify.py` — static checks per framework (syntax via tree-sitter or `node --check`, eslint if present, htmlhint for static)
- [ ] `helm/services/builder/explain.py` — Haiku-backed one-paragraph summary
- [ ] `helm/services/builder/orchestrator.apply_plan` — full flow (snapshot → execute → verify → explain)
- [ ] `helm/routes/builder.py` — `POST /builder/plans/{id}/approve` triggers apply

### Frontend

- [ ] `apps/web/components/builder/VerifyReport.tsx` — ✓ / ⚠ / ✗ with plain-English check names
- [ ] Plan Review UI updated: on approve, show applying → verify report → summary
- [ ] File drawer (collapsed by default): shows file tree of current version

### Verify

```
Smoke: approve → files land → verify pane shows ✓/⚠ → summary renders
```

---

## Phase B3 — Preview runtime

Goal: a live preview iframe. This is the big UX unlock.

### Backend

- [ ] `helm/services/builder/preview.py` — build file manifest, short-lived signed URL for hydration
- [ ] `helm/routes/builder.py` — `GET /builder/{id}/preview_manifest`
- [ ] `next.config.mjs` — cross-origin-isolation headers scoped to `/builder/:path*`

### Frontend

- [ ] `apps/web/components/builder/PreviewFrame.tsx` — WebContainer boot + mount + spawn dev server
- [ ] `apps/web/app/builder/[id]/page.tsx` — center pane: PreviewFrame, right: FileDrawer
- [ ] Install `@webcontainer/api` dependency
- [ ] Framework detection → select correct `npm run dev` command

### Verify

```
Smoke: blank project with Vite scaffold → preview boots → iframe renders hello-world
```

---

## Phase B4 — Undo + Publish (helm-hosted)

Goal: founder can undo the last change and publish the project to helm.app/apps/<slug>.

### Backend

- [ ] `helm/services/builder/versioning.undo_last` — restore previous_version_id file tree
- [ ] `helm/routes/builder.py` — `POST /builder/{id}/undo`
- [ ] `helm/services/builder/publisher.py` — static-build pipeline (WebContainer build → upload to Supabase Storage)
- [ ] `helm/routes/builder.py` — `POST /builder/{id}/publish/helm`
- [ ] `apps/web/app/apps/[slug]/page.tsx` — public route serving published projects
- [ ] Storage bucket `builder-public` created with public read policy

### Frontend

- [ ] `apps/web/components/builder/UndoButton.tsx` — one-click undo with confirm
- [ ] `apps/web/components/builder/PublishPanel.tsx` — slug input, Deploy button, status chip
- [ ] `apps/web/app/builder/[id]/publish/page.tsx` — panel page

### Verify

```
Smoke: apply change → undo → preview reverts
Smoke: publish → visit /apps/<slug> in new tab → content matches latest version
```

---

## Phase B5 — Import / export (GitHub + ZIP)

Goal: bring in existing code; push changes back.

### Backend

- [ ] Add `github` connector to `services/provider_catalog.py` (scope=account, auth=composio_oauth)
- [ ] `helm/services/builder/github_client.py` — clone via tarball API, push via Contents API
- [ ] `helm/routes/builder.py` — `POST /builder/import/github`, `POST /builder/import/zip`, `POST /builder/{id}/export/zip`, `POST /builder/{id}/export/github`
- [ ] ZIP unpack service (reuse existing `zipfile` stdlib, walk tree, write rows)

### Frontend

- [ ] New-project wizard: GitHub URL input + ZIP drop target
- [ ] PublishPanel: "Also push to GitHub" toggle (when connected) + repo picker

### Verify

```
Smoke: import a small public repo → files visible → preview boots → apply edit → export ZIP downloads → export GitHub pushes commit
```

---

## Phase B6 — Custom domain + polish

Goal: custom domain stub, analytics, daily cap, founder-language polish pass.

### Backend

- [ ] `publisher.py` — custom_domain column + DNS-instruction JSON response
- [ ] Daily spend cap enforcement in orchestrator
- [ ] Analytics events emitted from orchestrator

### Frontend

- [ ] PublishPanel: custom-domain form + CNAME instructions card
- [ ] DailySpendWarning component (60% soft, 100% hard)
- [ ] Founder-language copy pass across all Builder strings — **no** "commit", "rollback", "diff", "stack trace", "repo", "branch", "migration", "endpoint" user-facing

### Verify

```
Smoke: enter custom domain → CNAME card shows correct target
Smoke: simulate spend past cap → new plan POST returns 402
Grep pass: `grep -rE 'commit|branch|migration|diff|stack trace|repo' apps/web/components/builder apps/web/app/builder` returns zero user-facing matches
```

---

## Cross-phase definitions of done

- `ruff check` clean across `helm/routes/builder.py` + `helm/services/builder/`
- `mypy --strict` clean across the same
- `npx tsc --noEmit` clean across `apps/web`
- Alembic upgraded; schema round-trips
- `/openapi.json` includes `/builder/*` routes
- Founder-language audit passes (no dev jargon leaks)
- README updated in `docs/builder/`

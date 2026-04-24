# Builder — Spec

> Lovable-level ease with strong internal architecture. Surface simplicity, internal rigor. No AI slop.

## 1. Problem

Non-technical founders inside Helm need to build and edit their own digital products — websites, landing pages, full SaaS — without writing code. Today they'd go to Lovable / v0 / bolt / Replit Agent for this, leaving Helm entirely. Builder pulls that loop back into Helm so the same founder who runs ads, books revenue, and issues corporate cards can also *build the product* from one surface.

## 2. Thesis

- **Beginner-simple on top, architecturally serious underneath.**
- Founder language everywhere user-facing. Developer concepts (repos, branches, migrations, diffs, stack traces) hidden unless explicitly requested.
- Six internal layers, cleanly separated: **intent → plan → execute → verify → explain → version.**

## 3. Target user

Primary: a non-technical Helm founder. Thinks in outcomes:
- "add payments"
- "let users upload photos"
- "fix why signup is breaking"
- "publish this change"
- "undo — that broke it"

Does **not** think in repos, branches, migrations, dependency graphs.

Secondary: a technically-adept founder who wants Builder's AI speed but occasional code-level escape hatches (view diff, view file tree, commit to GitHub). These are available but not default.

## 4. Non-goals (v1)

- Multi-developer collaboration, comments, review queues.
- Automatic custom-domain TLS (stub + DNS instructions only).
- Server-side-rendered runtime preview for arbitrary Node apps. Preview is StackBlitz WebContainer (browser-side Node, handles Next/Vite/React/Vue/static out of the box; SSR w/ custom native deps = manual deploy).
- Cursor-level multi-turn in-file reasoning. v1 uses single-shot plan-then-apply.
- Full version history with branching. v1 is **one-step undo** (pre-write snapshot only).
- Realtime pair-programming with multiple users.

## 5. Core user journeys

### 5.1 New project from description
1. Founder opens `/builder`, clicks "New project"
2. Describes: "A landing page for my linen-goods DTC brand with a hero, product grid, newsletter signup, and pricing table."
3. Builder proposes: template (Vite + React), 4 pages, affected files, risks (none), recommendation
4. Founder clicks Approve
5. Builder generates files, opens workspace
6. Preview iframe boots (WebContainer); file tree visible in a collapsible drawer
7. Founder clicks Publish → picks helm-hosted URL or custom domain → deploy

### 5.2 Import existing project
1. Founder clicks "Import"
2. Pastes GitHub URL (requires GitHub connection) **or** uploads a ZIP
3. Builder clones/unpacks, detects framework, opens workspace
4. Founder describes edits in plain English; flow from 5.3 kicks in

### 5.3 Edit a project
1. Founder types: "Make the hero headline say 'Handmade linen for modern homes' and change the accent color to warm terracotta"
2. Builder proposes plain-English plan ("Update the hero headline and accent color. Two files touched.")
3. Founder approves
4. Builder writes snapshot (undo point), applies diff, re-runs preview
5. Review pane: summary, what changed in plain English, verification status (✓ syntax, ✓ lint, ⚠ 1 warning explained in English)
6. Founder can **Keep**, **Undo**, **Refine** (follow-up prompt), or **Publish**

### 5.4 Undo
- One click. Restores `previous_version_id` file tree. Preview re-boots.
- Only one undo step — after another change applies, the previous undo target is overwritten.

### 5.5 Export
- "Download ZIP" (public URL to presigned archive)
- "Push to GitHub" (requires GitHub connection; commits to linked repo's main branch with founder-written message)

### 5.6 Publish
- **Helm-hosted**: static build → served at `helm.app/apps/<slug>` via Helm's existing Next.js
- **Custom domain**: user enters `app.theirbrand.com` → Builder shows CNAME setup instructions → once DNS propagates, Helm issues Let's Encrypt cert via an existing worker (stub in v1; manual in first rollout)

## 6. Screens / information architecture

- `/builder` — project list. Cards show slug, last-edit time, status (draft / ready / published), screenshot thumbnail
- `/builder/new` — creation wizard (description OR import GitHub/ZIP)
- `/builder/[id]` — workspace:
  - **Left**: Ask/Plan/Review chat pane (chronological list of turns)
  - **Center**: Preview iframe with controls (refresh, fullscreen, device frame toggle)
  - **Right**: Optional drawer — file tree + plan details, collapsed by default to keep beginner mode clean
- `/builder/[id]/versions` — (v1: just "Undo last change") card; full history lives in the data model for v2
- `/builder/[id]/publish` — publish panel: URL slug, custom-domain form, Deploy button, last-deploy status

## 7. Domain model

```
builder_projects
  id, user_id, business_id?,
  name, slug, description,
  template ('blank'|'import_github'|'import_zip'),
  source_url? (github clone url)
  framework ('next'|'vite'|'static'|'react_cra'|'other'),
  status ('draft'|'ready'|'published'|'error'),
  github_repo_url?,         # connected repo for push-commit export
  published_url?,           # helm-hosted URL once published
  custom_domain?,           # user-owned domain
  current_version_id?,
  previous_version_id?,     # one-step undo target
  daily_spend_cents,        # resets per UTC day
  daily_spend_cap_cents,    # default $5 for free tier
  created_at, updated_at

builder_project_files
  id, project_id, version_id, path, content (text),
  binary_url?,              # for binary files (images, fonts) — stored in Supabase Storage
  hash, created_at

builder_versions
  id, project_id, parent_version_id?,
  label (nullable — v1 uses ISO timestamp),
  change_summary_plain, change_summary_technical,
  commit_sha?,              # if pushed to GitHub
  snapshot_manifest (jsonb: { path -> hash })
  created_at

builder_plans
  id, project_id, user_prompt,
  plain_plan, technical_plan,
  affected_areas (jsonb: [{ label, rationale }]),
  risks (text), recommendation (text),
  status ('proposed'|'approved'|'rejected'|'applied'|'failed'),
  applied_version_id?,
  created_at

builder_runs
  id, project_id, plan_id?,
  step ('intent'|'plan'|'execute'|'verify'|'explain'),
  model, input_tokens, output_tokens, cost_cents,
  status ('running'|'completed'|'failed'),
  output (jsonb), error?, created_at
```

## 8. Backend / service architecture

`services/builder/` package. Six siblings, each pure-ish (inputs → outputs), composed by a thin orchestrator.

```
services/builder/
  __init__.py
  intent.py          # prompt → {kind: 'create'|'edit'|'import'|'publish'|'undo', args}
  plan.py            # intent + project context → Plan row (plain + technical)
  execute.py         # approved Plan → file-level writes (with pre-snapshot)
  verify.py          # run syntax/tsc/lint on touched files; plain-English report
  explain.py         # produce the user-facing summary of what changed
  versioning.py      # snapshot + one-step undo
  orchestrator.py    # glues layers into a single "apply plan" entry point
  preview.py         # issue short-lived StackBlitz WebContainer tokens + manifest
  github_client.py   # clone / push via user's OAuth token
  frameworks.py      # detect framework from files (package.json heuristics)
```

### Data flow

```
  UI  ──POST /builder/{id}/plan──▶  orchestrator.propose_plan
                                         │
                                         ├─ intent.parse
                                         ├─ plan.generate (Claude Opus/Sonnet)
                                         └─ persist Plan (status='proposed')

  UI  ──POST /builder/plans/{id}/approve──▶  orchestrator.apply_plan
                                                  │
                                                  ├─ versioning.snapshot  (sets previous_version_id)
                                                  ├─ execute.apply        (LLM writes files)
                                                  ├─ verify.run           (syntax + lint)
                                                  ├─ explain.summarize    (plain-English delta)
                                                  └─ mark Plan applied, emit analytics

  UI  ──POST /builder/{id}/undo──▶  versioning.undo_last  (restores previous_version_id)

  UI  ──POST /builder/{id}/publish──▶  publisher.publish_helm_hosted or .publish_custom_domain
```

### LLM orchestration details

- **Plan** uses Opus 4.7 when the project has > 20 files **or** the prompt asks for architecturally-significant changes (keyword detect + file count heuristic). Otherwise Sonnet 4.6. Configurable via `HELM_BUILDER_PLAN_MODEL`.
- **Execute** uses Sonnet 4.6 by default (cheaper, faster; plan already did the hard thinking).
- **Verify / Explain** use Haiku 4.5.
- Every LLM call flows through `credits.reserve → commit/refund` so failures never charge.
- Hard cap: `builder_projects.daily_spend_cents` tracks day-local spend; new requests 402 once above cap.

### Preview runtime

- StackBlitz **WebContainer** — `@webcontainer/api` in the browser.
- Server issues a short-lived *project manifest* (file tree JSON) via `/builder/{id}/preview_manifest`.
- Browser boots the container, loads files, runs the framework's dev server, displays in iframe.
- Requires StackBlitz cross-origin-isolated headers (COEP/COOP) on the `/builder` route — add in `next.config.mjs`.

### GitHub integration

- OAuth via existing Composio integration layer. New `github` entry in `connectors/catalog` with scope=account, auth_mode=composio_oauth, required_scopes=`repo`.
- Clone: `git archive` via GitHub API → unzip → load into `builder_project_files`.
- Push: create commit via Contents API; one file per call is fine for a MVP.

## 9. Integration points with existing Helm systems

- **Credits** (`services/credits.py`): reserve/commit for every LLM call, same pattern as Canvas Studio.
- **Connections** (`services/connections*.py`): GitHub OAuth piggybacks the Composio integration layer.
- **Brand Library** (`services/brand_library.py`): on "new project from description," Builder reads the active business's Brand Library (palette, typography, voice) and injects it into the project's CSS variables + copy tone.
- **Storefront** (`storefronts_routes.py`): Builder projects with a detected "products grid" can import SKUs from Helm Storefront automatically (opt-in per project).
- **AppShell**: Builder lives under `/builder` at the top-level nav, not under `/studio`, because it's a peer pillar to Creative Studio.

## 10. Permissions / security

- Per-user project ownership. `business_id` is optional metadata.
- GitHub OAuth tokens stored encrypted via existing `integration_vault.py`.
- WebContainer iframe sandboxed (`sandbox="allow-scripts allow-same-origin"`, cross-origin-isolated).
- Published helm-hosted URLs served from a `/apps/*` subpath with restricted CSP (no parent-frame access to Helm session cookies).
- No arbitrary shell exposed to the founder; all "run" happens inside the WebContainer, not on Helm's servers.

## 11. Analytics events

- `builder_project_created`
- `builder_plan_proposed`, `builder_plan_approved`, `builder_plan_rejected`, `builder_plan_applied`, `builder_plan_failed`
- `builder_verify_passed`, `builder_verify_warned`, `builder_verify_failed`
- `builder_undo_used`
- `builder_published_helm_hosted`, `builder_published_custom_domain`
- `builder_imported_github`, `builder_imported_zip`
- `builder_github_pushed`

## 12. Feature flag + rollout

- Env flag `HELM_BUILDER_ENABLED` (default false in prod for initial weeks).
- Nav entry + routes gated on flag + `user.experiments.builder_beta=true`.
- Beta badge in nav and on `/builder` header.

## 13. Risks / tradeoffs

| Risk | Severity | Mitigation |
|------|----------|------------|
| WebContainer doesn't support a framework the founder imports | High | Detect unsupported frameworks on import; show a clear "preview unsupported — publish-only" state instead of broken iframe |
| LLM writes broken code | High | Always snapshot before write (one-step undo is safety net); verify step catches syntax + lint; "refine" loop lets founder iterate |
| Cost explosion in chatty edit session | Medium | Per-project daily cap; soft warning at 60% of cap, hard stop at 100% |
| Custom-domain TLS complexity | Medium | v1 stubs the flow with DNS instructions; automate in v2 with Let's Encrypt + cert storage |
| GitHub rate limits | Low | Use per-user OAuth tokens (5k req/hr); batch commits where feasible |
| Private code stored on Helm | Medium | All project file content encrypted at rest via existing Supabase Storage; OAuth tokens via integration_vault |

## 14. Verification plan

Exact commands run before declaring v1 done:

```
# Backend
/Users/jarvis/code/helm/.venv/bin/ruff check helm/routes/builder.py helm/services/builder/
/Users/jarvis/code/helm/.venv/bin/mypy --strict helm/services/builder/ helm/routes/builder.py
/Users/jarvis/code/helm/.venv/bin/alembic upgrade head
PYTHONPATH=. /Users/jarvis/code/helm/.venv/bin/python -c "from helm.main import app; print(len(app.routes))"

# Web
cd /Users/jarvis/code/helm/apps/web && npx tsc --noEmit

# End-to-end smoke
1. Create blank project named "smoke-test"
2. Ask: "Add a hero section with headline 'Hello Helm'"
3. Approve plan
4. Preview shows "Hello Helm"
5. Undo → preview reverts
6. Ask again: "Add a CTA button"
7. Verify → ✓ syntax, ✓ lint
8. Publish to helm-hosted URL → visit published URL → sees CTA
```

## 15. Phased plan (narrow v1)

See `BUILDER_V1_TASKLIST.md` for the file-level breakdown. High-level phases:

- **B0 — Foundation**: migration + models + service skeleton + routes + nav + shell
- **B1 — Plan flow**: `/builder` list, new project wizard, intent → plan UX, approval
- **B2 — Execute + verify**: LLM writes files, snapshot before, verify report in plain English
- **B3 — Preview runtime**: StackBlitz WebContainer boot + iframe
- **B4 — Undo + Publish (helm-hosted)**: one-step undo button, publish to `helm.app/apps/<slug>`
- **B5 — Import/export (GitHub + ZIP)**: GitHub OAuth, clone, push, ZIP upload/download
- **B6 — Custom domain stub + polish**: DNS instructions UI, founder-language copy pass, analytics events, per-project daily cap

V1 ships when B0–B4 are green. B5/B6 can ship on fast-follow.

## 16. Success criteria for v1

- A Helm founder signs in, clicks /builder, describes "A landing page for my coffee subscription," approves, sees a real preview, iterates once, publishes to `helm.app/apps/their-slug`, opens that URL in a new tab — all within 5 minutes, with zero mentions of the word "repo," "commit," or "migration" visible anywhere in the UI.

# DEPLOY.md — Phase 0 setup

What the user needs to do once to bring the Phase 0 skeleton online. Everything here is one-time; every subsequent deploy is a `git push` to `main`.

## 1. Create the Supabase project

1. Go to [supabase.com](https://supabase.com) → **New project**.
2. Region: `us-east` (closest to our Render region). Database password: generate and store in 1Password.
3. Once provisioned, enable the `vector` extension:
   - Dashboard → **Database** → **Extensions** → search for `vector` → toggle on.
   - (The Alembic migration will do this too if the extension is available, but flipping it in the UI removes a class of permission errors.)
4. Grab the values you'll need (Dashboard → **Project settings**):
   - **API** → `Project URL` → `SUPABASE_URL`
   - **API** → `anon public` → `SUPABASE_ANON_KEY`
   - **API** → `service_role secret` → `SUPABASE_SERVICE_ROLE_KEY`
   - **API** → `JWT Settings` → `JWT Secret` → `SUPABASE_JWT_SECRET` (optional — only needed if the project is still on HS256; new Supabase projects use asymmetric keys via JWKS and our backend prefers that path)
   - **Database** → `Connection string` → `URI` → copy, then:
     - replace the `postgresql://` prefix with `postgresql+asyncpg://`
     - this is your `DATABASE_URL`

## 2. Run migrations against Supabase

```bash
# from /Users/jarvis/code/helm
cp .env.example .env.local
# Fill in SUPABASE_* and DATABASE_URL in .env.local

pnpm migrate
```

Expected output: `INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial`.

Sanity check — in the Supabase Dashboard → **Table Editor** you should see: `users`, `businesses`, `agent_sessions`, `agent_events`, `approvals`, `agent_memories`, `integrations`, and `alembic_version`.

## 3. Create the Render service

1. Go to [render.com](https://render.com), sign up with GitHub, grant the Render app access to the `hellojarvis-droid/helm` repo.
2. **New → Blueprint** → pick the `helm` repo. Render will detect `render.yaml` and propose one service: `helm-api`.
3. Click **Apply**. Render will build the Docker image and start the service.
4. In **Environment → Add Environment Variable**, paste these (all from step 1, plus secrets):
   - `DATABASE_URL` (same as local)
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_JWT_SECRET` (optional)
   - `SENTRY_DSN` (optional — can leave blank; will add when we create the Sentry project)
   - `ANTHROPIC_API_KEY` (can leave blank until Phase 1)
   - `COMPOSIO_API_KEY` (Phase 1)
   - `STRIPE_SECRET_KEY` (Phase 2; keep `sk_test_` only)
   - `STRIPE_WEBHOOK_SECRET` (Phase 2)

5. Trigger a redeploy (Render does this automatically on env-var change).
6. Once the build is green, hit `https://helm-api.onrender.com/health` (or whatever subdomain Render assigned) — expect:

   ```json
   { "status": "ok", "service": "helm-api", "version": "0.0.0", "env": "staging" }
   ```

## 4. Connect the repo to CI

GitHub Actions CI runs automatically on every push + PR — no setup needed. The first run on `main` will spin up a pgvector/pg16 Postgres service, run ruff/mypy/pytest, and run a noop web job (will grow in Phase 4).

## 5. What's still manual (and will stay manual until Phase 1+)

- **Anthropic Managed Agents beta access** — you apply, not Claude Code.
- **Stripe Issuing for Agents** — you apply; Phase 2 is blocked on approval.
- **Shopify Agentic Plan** — you apply; Phase 3 is blocked on approval.
- **Sentry project** — you create, grab the DSN, drop into Render env.
- **Domain** — skipped for staging per decision; will revisit when we flip live.

## 6. Supabase RLS — not required for Phase 0

Our backend uses the `service_role` key, which bypasses RLS. Tenant isolation is enforced by the ORM session (`helm.db.tenant.*` helpers) and tested in `test_tenant_isolation.py`. We'll layer RLS policies on top in Phase 1 as belt-and-braces once clients start talking directly to Supabase for Realtime.

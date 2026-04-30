# Helm — handoff to Joseph's MacBook Pro

Generated 2026-04-22 from `/Users/jarvis/code/helm`.

## What's in this archive

Full source + configs + docs. **No secrets** — `.env.local` is NOT
included. A companion `helm-env-template.txt` on your Desktop lists every
variable name with empty values; paste the real values through your
password manager on the receiving Mac.

Excluded (all regeneratable):
- `node_modules/`, `.venv/`, `apps/web/.next/`
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`
- `dist/`, `build/`, `.DS_Store`
- Playwright / pnpm caches

## To resume work on Joseph's Mac

```bash
# 1. Install toolchain if needed
brew install uv pnpm node

# 2. Extract + set up env
unzip ~/Downloads/helm-transfer-*.zip -d ~/code/
cd ~/code/helm
# Copy the env template + paste real values from your password manager:
cp helm-env-template.txt .env.local
$EDITOR .env.local

# 3. Install deps
pnpm install
cd apps/api && uv sync && cd ../..

# 4. DB migrations (shared Supabase, usually already at head)
cd apps/api && uv run alembic upgrade head && cd ../..

# 5. Start services (two terminals)
# API:
cd apps/api && uv run uvicorn helm.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload
# Web:
cd apps/web && pnpm dev
```

Sign in at `http://localhost:3000` with `hellojarvisai1@gmail.com`.

## Where to pick up (as of 2026-04-22)

- **Builder feature** — all phases B0–B6 shipped. Live StackBlitz
  WebContainer preview, one-step undo, publish to `/apps/<slug>`, GitHub
  public-repo import, ZIP import/export, custom-domain stub.
- **Canvas Creative Studio** — all phases done.
- **Last bug fixed**: preview hang. Root causes were `host: true` in the
  Vite template and Builder CSP missing `http://localhost:8000` in
  `connect-src`. Preview now boots end-to-end in ~8s.

## Test harness

```bash
cd apps/web
HELM_TEST_PASSWORD='<pw>' node scripts/builder_e2e_test.mjs
```
Signs in, hits `/builder/probe`, creates a project via API, watches the
Vite preview load in WebContainer. Passes in <30s.

## Docs

- `docs/builder/SPEC.md` · `BUILDER_ARCHITECTURE.md` · `BUILDER_V1_TASKLIST.md`
- `docs/PRD.md` · `ARCHITECTURE.md` · `AGENTS.md` · `UI_DESIGN.md`

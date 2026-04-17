# Helm

Agent-native operating system for serial entrepreneurs. One CEO Agent, a swarm of specialists, three surfaces (mobile + desktop + web), real Stripe-issued virtual cards with programmatic spend controls.

**Status:** Phase 0 — foundations. See `docs/BUILD_PLAN.md` for the roadmap.

## The docs

Start with [`CLAUDE.md`](./CLAUDE.md), then read these in order:

1. [`docs/PRD.md`](./docs/PRD.md) — what we're building and for whom
2. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — stack and system design
3. [`docs/AGENTS.md`](./docs/AGENTS.md) — every agent's prompt and tools
4. [`docs/UI_DESIGN.md`](./docs/UI_DESIGN.md) — design principles
5. [`docs/BUILD_PLAN.md`](./docs/BUILD_PLAN.md) — phase-by-phase build order
6. [`docs/INTEGRATIONS.md`](./docs/INTEGRATIONS.md) — Composio + external services

## Repo layout

```
helm/
├── apps/
│   └── api/            # Python FastAPI backend (current)
│                       # web, desktop, mobile, workers land in Phase 4
├── packages/           # Shared UI + types + design tokens (Phase 4)
├── infra/              # Temporal workflows, deploy configs
├── docs/               # Source-of-truth specs
├── config/             # composio-toolkits.json etc.
└── examples/           # seed-business.py etc.
```

## Local dev — Phase 0

**Prereqs:**

- Node 20+ (`.nvmrc`), pnpm 9+ (`corepack enable && corepack prepare pnpm@9.15.2 --activate`)
- `uv` for Python (`brew install uv` — Python 3.12 is provisioned by uv on first run)
- A Supabase project (free tier is fine for dev)
- A running Postgres 16 with the `pgvector` extension — Supabase provides this

**Setup:**

```bash
cp .env.example .env.local
# fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL

pnpm install                          # JS/TS workspaces (minimal for now)
cd apps/api && uv sync                # Python deps (first run installs Python 3.12)

# Run migrations against Supabase
pnpm migrate

# Start the API
pnpm api:dev                          # http://localhost:8000/health
```

**Tests + quality:**

```bash
pnpm api:test       # pytest
pnpm api:lint       # ruff check
pnpm api:typecheck  # mypy --strict
pnpm format         # prettier across the monorepo
```

## Deploy (staging)

Backend ships to [Render](https://render.com) as a Blueprint — see [`render.yaml`](./render.yaml). Supabase hosts Postgres + Auth + Realtime + Storage.

## Contributing

- Branches: `feat/*`, `fix/*`, `chore/*`
- Commits: Conventional Commits, scoped per workspace (e.g. `feat(api): ...`)
- CI must pass before merge
- Tests ship with features, not after

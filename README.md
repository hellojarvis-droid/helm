# Helm

Agent-native operating system for serial entrepreneurs. One CEO Agent, eight specialists, three surfaces (mobile + desktop + web), real Stripe-issued virtual cards with programmatic spend controls.

**Status:** Phase 2 money spine + Phase 3 commerce spine + Phase 5 agent swarm shipped. 8/8 specialists real. Three surfaces: mobile (Expo) + web (Next.js 15) live; desktop (Tauri) is the remaining surface. See [`docs/BUILD_PLAN.md`](./docs/BUILD_PLAN.md) for the dependency graph.

## The docs

Start with [`CLAUDE.md`](./CLAUDE.md), then read these in order:

1. [`docs/PRD.md`](./docs/PRD.md) — what we're building and for whom
2. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — stack and system design
3. [`docs/AGENTS.md`](./docs/AGENTS.md) — every agent's prompt and tools
4. [`docs/UI_DESIGN.md`](./docs/UI_DESIGN.md) — design principles
5. [`docs/BUILD_PLAN.md`](./docs/BUILD_PLAN.md) — phase-by-phase build order
6. [`docs/INTEGRATIONS.md`](./docs/INTEGRATIONS.md) — Composio + external services
7. [`docs/DEPLOY.md`](./docs/DEPLOY.md) — Render + Supabase + Vercel

## Repo layout

```
helm/
├── apps/
│   ├── api/            # Python 3.12 FastAPI — CEO runtime, specialists,
│   │                   # Stripe Connect + Issuing, approvals, event log
│   ├── web/            # Next.js 15 App Router — Today / Chat / Businesses /
│   │                   # Approvals / Safety / Billing + marketing landing
│   └── mobile/         # Expo SDK 52 — the same five surfaces for phone,
│                       # push notifications, haptics, SSE-streamed chat
├── packages/           # (reserved for Phase 4 shared design tokens)
├── docs/               # Source-of-truth specs
└── render.yaml         # API deploy (Render Blueprint)
```

## What's shipped

- **CEO runtime** — Anthropic Messages API (Opus 4.7 orchestrator, Sonnet 4.6 specialists, Haiku 4.5 volume) with a streaming tool-use loop. Events land in Postgres; SSE streams them to web + mobile.
- **Eight specialists** — Idea Scout, Product Builder, Creative Director, Ads Operator, Growth Analyst, Social Engagement, Customer Service, Finance & Ops. All real LLMSpecialists using Composio-mediated tools.
- **Money spine** — Stripe Connect onboarding, Issuing card per business, authorization webhook with kill-switch / MCC / per-auth / weekly-cap decision tree. Revenue tracked via `payment_intent.succeeded`.
- **Approvals** — threshold-coded `request_user_approval`. Money-first spend card with amount, merchant, purpose + "Approve / Approve & raise cap / Deny" options. Cap raise mirrors to Stripe's own `spending_limits`.
- **Hard rule #2 — Kill switch** — global user-level flag with 1s TTL cache. Checked before every tool call. Surfaced on every tab as a banner when on; full controls on the Safety tab. Blocks Stripe authorizations at the webhook.
- **Three observability stacks** — Sentry (errors, all surfaces), Langfuse (LLM traces + cost per session), PostHog (product analytics on web + mobile).
- **Billing** — tier limits (Founder / Operator / Portfolio) enforced at write-time. Stripe Checkout upgrade flow + Customer Portal for self-serve management. Subscription webhooks keep `user.tier` in sync.
- **Push** — Expo push notifications fire when approvals land; tapping deep-links into the Approvals tab.

## Local dev

**Prereqs:**

- Node 20+ (`.nvmrc`), pnpm 9+ (`corepack enable && corepack prepare pnpm@9.15.2 --activate`)
- `uv` for Python (`brew install uv` — Python 3.12 is provisioned by uv on first run)
- A Supabase project (free tier is fine for dev)
- A running Postgres 16 with the `pgvector` extension — Supabase provides this

**Setup:**

```bash
cp .env.example .env.local
# fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL
# + ANTHROPIC_API_KEY, COMPOSIO_API_KEY, STRIPE_SECRET_KEY

pnpm install
cd apps/api && uv sync

pnpm migrate              # Alembic against Supabase
pnpm api:dev              # http://localhost:8000/health
pnpm web:dev              # http://localhost:3000
cd apps/mobile && pnpm start   # Expo Go for phone, or w for web
```

**Tests + quality:**

```bash
pnpm api:test       # pytest (needs TEST_DATABASE_URL pointing at a PG with pgvector)
pnpm api:lint       # ruff check
pnpm api:typecheck  # mypy --strict
pnpm typecheck      # TS typecheck across web + mobile
pnpm format         # prettier across the monorepo
pnpm format:check   # CI gate
```

## Deploy

- **API** — Render Blueprint ([`render.yaml`](./render.yaml)). Auto-deploys on push to `main`.
- **Web** — Vercel.
- **Mobile** — Expo EAS builds for TestFlight / Play internal track.
- **Postgres + Auth** — Supabase.
- **Staging URL** — see `docs/DEPLOY.md` for the current hosts.

## Contributing

- Branches: `feat/*`, `fix/*`, `chore/*`
- Commits: Conventional Commits, scoped per workspace (e.g. `feat(api): ...`, `feat(web+mobile): ...`)
- CI must pass before merge. `pnpm format:check` and `pnpm typecheck` and `uv run pytest` are the three gates.
- Tests ship with features, not after.

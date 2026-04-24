# CLAUDE.md — Helm Build Instructions

> You are Claude Code, building **Helm** — a premium, agent-native platform that helps serial entrepreneurs brainstorm, launch, and autonomously operate businesses from one command surface that spans mobile, desktop, and web.
>
> Read this file first. Then read `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/AGENTS.md`, `docs/UI_DESIGN.md`, and `docs/BUILD_PLAN.md`. When you finish reading, post a one-paragraph "understood" summary to the user before writing any code. Then begin executing `docs/BUILD_PLAN.md` in order.

---

## 1. What Helm Is (One Paragraph)

Helm is the operating system for one-person holding companies. The user — a serial entrepreneur — talks to a single "CEO Agent" from their phone. That agent orchestrates a swarm of specialist sub-agents (Idea Scout, Product Builder, Creative Director, Ads Operator, Social Engagement, Customer Service, Finance, Growth Analyst) that handle every facet of a business end-to-end: pick proven ideas, spin up the product and storefront, run ads with autonomous budget control, engage customers, track every dollar through a single issued virtual card, and react in real time to churn/bad spend/feedback. The mobile app is a Dispatch-style command surface. The desktop app has full computer-use capability for tasks that need a screen. The web app is the deep-dive dashboard. All three are one product, not three.

## 2. Non-Negotiable Decisions (Don't Bikeshed)

These are settled. Do not propose alternatives unless you find a concrete blocker.

| Concern | Decision |
|---|---|
| **Agent runtime** | Claude Managed Agents (hosted) + Claude Agent SDK (Python) for dev |
| **Primary model** | Claude Opus 4.7 for orchestrator & strategy; Sonnet 4.6 for execution; Haiku 4.5 for high-volume actions |
| **Integration layer** | **Composio** as the unified MCP gateway (500+ toolkits, managed OAuth). Direct MCP servers only for Stripe, Shopify, and our own custom skills. |
| **Money spine** | Stripe Connect (one connected account per business) + Stripe Issuing (virtual card per business with programmatic spend controls) |
| **Commerce spine** | Shopify Admin API (via the Shopify AI Toolkit MCP) for DTC; Stripe Billing for SaaS |
| **Backend** | Python 3.12, FastAPI, Temporal for durable workflows, Supabase Postgres 16 (with `tenant_id` on every row), pgvector for agent memory |
| **Auth + data** | **Supabase** (Auth, Postgres 16 with pgvector, Realtime, Storage) — replaces Clerk + Fly Postgres from the original kit. OAuth-to-Stripe/Shopify/Composio handled by Composio where possible. WorkOS is the enterprise upgrade path. |
| **Secrets** | Doppler or Infisical. Never store API keys in the agent context — agents request ephemeral tokens from a vault service. |
| **Observability** | Langfuse for LLM traces + cost, Sentry for errors, PostHog for product analytics |
| **Desktop app** | Tauri (Rust + web frontend). Not Electron. Smaller binary, native feel, better security model. |
| **Mobile app** | Expo (React Native) with native modules for iOS Live Activities, Siri Shortcuts, Android widgets. Plan a native Swift/Kotlin rewrite in month 6 once we know what matters. |
| **Web app** | Next.js 15 App Router, React Server Components, Tailwind 4, shadcn/ui as the base + custom premium components |
| **Shared UI** | Extract shared React components into a `packages/ui` workspace. Tauri and Next.js both consume it. Mobile has its own RN equivalents but matches the design tokens. |
| **Monorepo** | Turborepo with pnpm workspaces |
| **Deployment** | Backend on **Render** (Blueprint in `render.yaml`; not AWS — we want speed, not IAM archaeology). Frontend on Vercel. Postgres hosted by Supabase. |
| **Testing** | Vitest for unit, Playwright for E2E, pytest for Python. No "we'll add tests later" — tests ship with features. |

## 3. Hard Rules

1. **Multi-tenant from line 1.** Every database table has `business_id` and `user_id`. Every agent call carries a tenant context. No exceptions. We will regret this if skipped.
2. **Money has a kill switch.** A single `PAUSE_ALL_AGENTS` flag at the user level must stop every running agent across every business in <2 seconds. This is implemented before any agent touches live money.
3. **No secrets in agent context.** Agents never see raw API keys. They call a vault service that returns a scoped, time-bound token per action. This is a security requirement, not a nice-to-have.
4. **Every agent action is logged.** Event-sourced. User can replay any decision. Used for debugging + compliance + trust.
5. **Approval tiers are code, not vibes.** Spend >$100 = approval required. Deleting customer data = approval required. Publishing to social = approval required. These are enforced at the orchestrator level and cannot be overridden by a sub-agent.
6. **Feel premium.** If a screen looks like a form, you did it wrong. Read `docs/UI_DESIGN.md` before designing any screen.
7. **Ship all three surfaces together.** Do not build web first and bolt on mobile. The data model and API surface must serve all three from day one.
8. **Never invoke the managed-agents sandbox for something a direct API call can do.** Sandboxed browser use is slow and expensive. Always prefer a Composio-mediated API call. Only fall back to computer use when there is no API.

## 4. How to Work

### When you're confident, execute. When you're not, ask.

You have broad latitude. Make small decisions yourself. For decisions that would change the product's identity, cost >$100/mo to reverse, or affect security/privacy — ask the user in chat with two concrete options and a recommendation.

### Build order is a dependency graph, not a timeline

`docs/BUILD_PLAN.md` lists work in dependency order. You can parallelize within a phase. You cannot skip ahead past a dependency.

### Commit discipline

- One logical change per commit. Conventional Commits format.
- Branch names: `feat/<short-description>`, `fix/<...>`, `chore/<...>`.
- Open a PR when a phase milestone completes, even against yourself, so the user can review diffs.

### When you finish a phase

Post to the user:
1. What's now working end-to-end
2. What you punted on and why
3. A 1-minute video script for a demo (text is fine; assume someone else records it)
4. The next phase's first three tasks

### Code quality bar

- TypeScript strict mode, no `any` unless commented with a reason.
- Python: type hints everywhere, `mypy --strict`, Ruff formatted.
- No `TODO` comments without a GitHub issue number.
- Every function >20 lines gets a docstring or JSDoc explaining *why*, not what.
- If you catch yourself writing a 300-line function, stop and refactor.

### When you're stuck

1. Re-read the relevant doc file.
2. Search the repo for existing patterns.
3. Run the feature end-to-end in your head before writing the test.
4. If you still can't, post a brief "I'm stuck on X, options are Y and Z, recommending Y because…" to the user and wait.

## 5. Secrets & Environment

A `.env.example` lives at the repo root. Every new service that needs a secret adds its variable there with a comment. Never commit real secrets. The user will fill in `.env.local` before running anything.

Required secrets at minimum:
- `ANTHROPIC_API_KEY`
- `COMPOSIO_API_KEY`
- `STRIPE_SECRET_KEY` (platform)
- `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / (optional) `SUPABASE_JWT_SECRET`
- `DATABASE_URL` (Supabase Postgres connection string)
- `TEMPORAL_ADDRESS`
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
- `SENTRY_DSN`
- `POSTHOG_KEY`

Per-business secrets (Shopify tokens, Meta Ads tokens, etc.) come through Composio's managed-auth flow — we never touch them directly.

## 6. The First Thing You Do

After reading the docs:

1. Create the Turborepo monorepo structure per `docs/ARCHITECTURE.md` §4.
2. Stand up the backend skeleton with a single `GET /health` endpoint.
3. Connect it to Supabase Postgres with a migration that creates the `users`, `businesses`, `agent_sessions`, `agent_events`, `approvals`, `agent_memories`, and `integrations` tables (see `docs/ARCHITECTURE.md` §5).
4. Wire up Supabase Auth (JWT validation via JWKS, with HS256 fallback).
5. Deploy to Render staging so the user can see it's alive.
6. Report back before continuing.

This whole step should take one session. If it's taking longer, you're over-engineering.

## 7. Product Naming

Working name: **Helm**. Domain: check `helm.ai` (likely taken — propose 3 alternatives). The user will pick the final name before public launch. Until then, use `Helm` everywhere in code, branding, and copy.

## 8. End-of-Task Workflow: `/handoff`

Before reporting any meaningful task complete, run the **handoff chain** defined in `~/.claude/commands/handoff.md`:

1. `git status --short && git diff --stat` — confirm there's real work to review.
2. `codex exec -s read-only "…"` — Codex (GPT-5.4) does an advisory review of the uncommitted diff. Apply findings you agree with; surface disagreements to the user.
3. `cursor-agent -p --force --trust "…"` — Cursor does a style/clarity polish pass (no logic changes).
4. `pnpm typecheck && pnpm lint && pnpm test` — verify nothing broke. Fix, don't paper over.
5. One-paragraph summary to the user: what you built, what Codex caught, what Cursor polished, what's verified passing. No raw tool output.

Skip for trivial edits only (one-line typos, comments, config tweaks). The full chain applies to every real feature/fix/refactor. See `~/.claude/commands/handoff.md` for exact prompts and failure handling.

---

*This document is the source of truth. If another doc contradicts this one, this one wins and the other doc gets updated.*

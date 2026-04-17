# BUILD_PLAN.md — How to Build Helm

This is the dependency graph Claude Code works through. Phases can parallelize *within* themselves. Phases cannot start before their predecessors finish.

Expected elapsed time: **10 weeks** with Claude Code working ~8 productive hours/day, with the user available for async review and unblock. Could compress with a team.

---

## Phase 0 — Foundations (Week 1)

**Goal:** empty repo → deployed skeleton the user can hit.

### 0.1 Repository and tooling
- [ ] Initialize Turborepo with pnpm + uv workspaces per `docs/ARCHITECTURE.md` §3
- [ ] Set up CI on GitHub Actions: lint, type check, test, build on every PR
- [ ] Configure Ruff, mypy, ESLint, Prettier with strict settings
- [ ] Add `.env.example` with every required variable documented
- [ ] Write root `README.md` that links all docs

### 0.2 Backend skeleton
- [ ] `apps/api` with FastAPI, single `GET /health` endpoint
- [ ] Postgres connection via SQLAlchemy 2.0 async
- [ ] Alembic migration 001: create `users`, `businesses`, `agent_sessions`, `agent_events`, `approvals`, `agent_memories`, `integrations` tables per schema in `docs/ARCHITECTURE.md` §5
- [ ] Temporal client connection stub (not using workflows yet, just proving connection)
- [ ] Pydantic models with tenant_id enforcement at the ORM level
- [ ] Integration test: cross-tenant query returns empty (security baseline)

### 0.3 Auth
- [ ] Clerk backend SDK integration
- [ ] Middleware: every authenticated request has `current_user` and `current_businesses` resolved
- [ ] `POST /auth/sync` creates a `users` row on first Clerk sign-in

### 0.4 Deployment
- [ ] Fly.io app for API (staging region us-east)
- [ ] Fly Postgres attached
- [ ] Deploy script with GitHub Actions (push to `main` → deploy staging)
- [ ] Send the user the staging URL when it's green

### 0.5 Observability baseline
- [ ] Sentry wired on backend + placeholder frontend
- [ ] Langfuse integration library installed (not yet sending data; that comes when agents are added)
- [ ] Request logging with correlation IDs

**Exit criteria:** user can curl `https://helm-api-staging.fly.dev/health` and see `{"status":"ok"}`. Clerk signup flow works. Database migrations run cleanly.

---

## Phase 1 — The Agent Backbone (Week 2)

**Goal:** the CEO Agent responds to messages from a CLI client. No UI yet.

### 1.1 Composio integration
- [ ] Composio Python SDK configured with platform API key
- [ ] `services/composio_client.py` wrapper that handles tenant-scoped tool retrieval
- [ ] `POST /integrations/{toolkit}/connect` endpoint that returns a Composio auth URL
- [ ] Webhook receiver for Composio connection-complete callbacks
- [ ] Integration test: connect Gmail via Composio end-to-end (use a test account)

### 1.2 Claude Managed Agents setup
- [ ] Anthropic API key provisioned, `managed-agents-2026-04-01` beta header set
- [ ] `services/managed_agents.py` that creates agents, environments, and sessions
- [ ] Create the CEO Agent definition per `docs/AGENTS.md` §1 (system prompt, tools list)
- [ ] Session lifecycle: on user first login, create their CEO Agent session; store session ID on the user row

### 1.3 The delegate_to_specialist primitive
- [ ] Tool definition for the orchestrator
- [ ] On call: looks up the specialist agent definition, creates a short-lived session with the business context, runs the task, returns the result
- [ ] Specialists start as stubs that return hardcoded-but-plausible outputs
- [ ] Temporal workflow wrapping: delegate_to_specialist becomes a Temporal activity with retry

### 1.4 The approval primitive
- [ ] `request_user_approval` tool implementation
- [ ] Inserts `approvals` row, sends notification (email only for now — push comes later)
- [ ] Tool returns a "pending" result that blocks agent progress
- [ ] `POST /approvals/{id}/respond` endpoint that resumes the agent session
- [ ] 24h expiration handling via Temporal timer

### 1.5 The event log
- [ ] Every tool call writes an `agent_events` row (synchronous insertion inside the tool wrapper)
- [ ] Every user message + agent response writes an event
- [ ] `GET /businesses/{id}/events` endpoint with pagination
- [ ] Cost tracking: every LLM call logs token counts + dollar cost

### 1.6 Kill switch
- [ ] `user.kill_switch_active` column
- [ ] Redis mirror with 1s TTL for fast reads
- [ ] Every agent tool wrapper checks the flag before execution, raises `KillSwitchActivated` if set
- [ ] `POST /users/me/kill_switch` endpoint (toggle on/off)
- [ ] Test: toggle on → next tool call fails within 2s

### 1.7 A working chat endpoint
- [ ] `POST /chat` receives a user message, routes to the CEO Agent session, streams response via SSE
- [ ] Messages stored in `agent_events` (event_type='message')
- [ ] Python CLI client in `examples/chat_cli.py` for testing

**Exit criteria:** user can run `python examples/chat_cli.py` and have a real conversation with the CEO Agent, including delegation to stub specialists, approvals via email, and see everything in the event log.

---

## Phase 2 — The Money Spine (Week 3)

**Goal:** Stripe Connect + Issuing working end-to-end. A test business can receive money and an agent can spend money with controls.

### 2.1 Stripe platform setup
- [ ] Stripe account in platform mode
- [ ] Apply for Issuing-for-agents access (this may take days; start early)
- [ ] Test mode configuration

### 2.2 Stripe Connect onboarding
- [ ] `POST /businesses` creates a Stripe connected account (Custom type)
- [ ] Stripe Connect onboarding link flow: user completes on web/mobile
- [ ] Webhook handler: `account.updated` keeps our DB in sync
- [ ] Integration test: create a test connected account end-to-end

### 2.3 Stripe Issuing
- [ ] Cardholder creation per business
- [ ] Virtual card issuance with configured spending_controls:
  - Weekly cap from `business.weekly_spend_cap_cents`
  - Allowlist of merchant categories: ads platforms, domain registrars, hosting, suppliers
  - Per-auth max of $500 default
- [ ] Real-time authorization webhook: `issuing_authorization.request` → Python handler decides approve/decline
- [ ] Decline reasons logged as `agent_events` with event_type='spend_declined'

### 2.4 The agent spend flow
- [ ] New tool: `spend_from_business_card(business_id, amount_cents, merchant_hint, purpose)`
- [ ] Tool creates a Shared Payment Token (via ACP) or returns card details via the secure vault
- [ ] Logged as `agent_events` event_type='spend'
- [ ] Agent-side cap: soft-reject anything >$100 without `request_user_approval`

### 2.5 Revenue tracking
- [ ] Webhook: `payment_intent.succeeded` on a connected account → business revenue event
- [ ] Daily aggregation job (Temporal) writes daily revenue summaries
- [ ] `GET /businesses/{id}/finances` endpoint with daily/weekly/monthly rollups

**Exit criteria:** End-to-end test — create a business, have the agent "spend" $10 on a test transaction, see the card charged, see the event logged, see the approval required when trying to spend >$100.

---

## Phase 3 — The Commerce Spine + First Real Specialist (Week 4)

**Goal:** Product Builder can actually create a live Shopify store. No more stubs.

### 3.1 Shopify integration
- [ ] Shopify Partners account + Shopify AI Toolkit enabled
- [ ] Composio SHOPIFY toolkit connected
- [ ] OR: direct Shopify Admin API via our own MCP wrapper if Composio's Shopify is insufficient
- [ ] Test: create a development store via API

### 3.2 Product Builder implementation
- [ ] Replace stub with real implementation per `docs/AGENTS.md` §3
- [ ] System prompt loaded from `packages/agents/specialists/product_builder.py`
- [ ] Skills bundled:
  - `ship-shopify-policies` (privacy, ToS, shipping, returns templates)
  - `lighthouse-check`
  - `dns-verify`
- [ ] End-to-end: from a concept description, produces a live store in <15 min

### 3.3 Creative Director (minimum viable)
- [ ] Brand kit generation: logo (via image gen), palette, typography pairing, voice guidelines
- [ ] Product description generator
- [ ] Hero image generator (Nano Banana via Composio)
- [ ] Stored in `businesses.brand_kit` JSONB

### 3.4 Domain + supplier
- [ ] Composio: Namecheap or Google Domains
- [ ] Composio: Printful (POD) and CJ Dropshipping
- [ ] Product Builder can query supplier, pick SKUs, load to Shopify

### 3.5 First real launch
- [ ] `examples/seed-business.py` creates a real test business end-to-end
- [ ] Manual QA: run it, verify the store is live, verify checkout works

**Exit criteria:** the user can type "Start a candle store" into the CLI chat and get a live, working Shopify store at a real domain within 15 minutes.

---

## Phase 4 — The Three Surfaces (Weeks 5-6)

**Goal:** all three surfaces — mobile, desktop, web — alive and synced. Chat works on all three.

Work can parallelize here. Priority order: **Mobile → Web → Desktop**.

### 4.1 Mobile (Expo)
- [ ] `apps/mobile` with Expo SDK 52
- [ ] Clerk Expo provider
- [ ] Single chat screen (primary surface)
- [ ] Approval card UI as a first-class component
- [ ] Push notifications (APNs + FCM) for approvals and digests
- [ ] Voice input (Expo AV + OpenAI Whisper or iOS built-in)
- [ ] Today screen: revenue, spend, pending approvals
- [ ] Business switcher
- [ ] Kill switch button (accessible from settings, one tap)

### 4.2 Web (Next.js 15)
- [ ] `apps/web` with App Router
- [ ] Clerk Next.js middleware
- [ ] Chat surface (primary) + dashboard sections per `docs/UI_DESIGN.md` §7
- [ ] shadcn/ui base, design tokens from `packages/design-tokens`
- [ ] Realtime chat sync (SSE)
- [ ] Dashboard: Today, Businesses, Agents, Approvals, Money, Events, Settings

### 4.3 Desktop (Tauri)
- [ ] `apps/desktop` with Tauri 2.0
- [ ] Shares React components with web via `packages/ui`
- [ ] Local IPC bridge for computer-use hand-off
- [ ] Menu bar icon + quick-access popover
- [ ] Auto-updater configured (Tauri's updater plugin)
- [ ] macOS code signing + notarization in CI
- [ ] Windows code signing (procure cert)

### 4.4 Shared chat state
- [ ] Chat thread is stored server-side as `agent_events`
- [ ] All three surfaces subscribe to the same SSE stream per user
- [ ] Optimistic UI on input; resolves against server state
- [ ] Offline-tolerance on mobile (queue outgoing messages)

**Exit criteria:** the user can start a conversation on mobile, continue on desktop, review on web. All three show the same live data.

---

## Phase 5 — The Full Agent Swarm (Week 7)

**Goal:** every specialist from `docs/AGENTS.md` is live, not stubbed.

Work in parallel where possible. Priority order based on user-visible impact:

### 5.1 Ads Operator (highest priority after Product Builder)
- [ ] Meta Ads via Composio — full campaign lifecycle
- [ ] Google Ads via Composio
- [ ] TikTok Ads via Composio (may need computer-use fallback for small-budget flows)
- [ ] Daily optimization cron (Temporal schedule)
- [ ] Budget reallocation skill

### 5.2 Idea Scout
- [ ] Proprietary trend data MCP (custom — see `docs/INTEGRATIONS.md`)
- [ ] Amazon BSR scraper (custom MCP)
- [ ] Reddit + TikTok trend queries via Composio
- [ ] Scoring algorithm
- [ ] Fit matching to user constraints

### 5.3 Social Engagement
- [ ] Instagram, TikTok, X, LinkedIn, Threads via Composio
- [ ] 2-min polling for new comments/DMs (Temporal schedule)
- [ ] Sentiment classification
- [ ] Reply vs. escalate decision tree

### 5.4 Customer Service
- [ ] Gorgias and Intercom via Composio
- [ ] Shopify orders via Shopify Admin API
- [ ] Refund logic with approval thresholds
- [ ] Escalation to user for edge cases

### 5.5 Finance & Ops
- [ ] Daily reconciliation job
- [ ] Weekly cash report generator
- [ ] QuickBooks + Xero via Composio
- [ ] P&L generator skill
- [ ] Anomaly detection (unusual merchants, spend spikes)

### 5.6 Growth Analyst
- [ ] Weekly strategic review (Sunday 6pm user-local)
- [ ] Anomaly detection on key metrics
- [ ] Recommendation generator
- [ ] Output format: compact deck (Markdown with embedded mini-charts)

**Exit criteria:** `examples/seed-business.py` launches a business and all agents operate it autonomously for 7 days with sensible actions (verified by human review of the event log).

---

## Phase 6 — Computer Use (Week 8)

**Goal:** Desktop app can drive the user's screen for tasks without APIs.

### 6.1 Computer-use agent session
- [ ] Managed Agents with `computer_use` tool enabled
- [ ] Sandboxed environment with network allowlist (only to the sites needed for the task)
- [ ] Tauri app streams the screen back to the user for observation
- [ ] Permission prompts for sensitive sites

### 6.2 Escalation flow
- [ ] Specialist agents can call `escalate_to_computer_use(task, app_hint)`
- [ ] Task queued → desktop app picks it up → runs → returns result
- [ ] If desktop app offline, task runs on Helm-hosted sandbox and desktop shows replay

### 6.3 Integration with existing specialists
- [ ] Ads Operator uses computer-use for TikTok small-budget flows
- [ ] Product Builder uses computer-use for supplier portals without APIs
- [ ] Fallback is always API-first, computer-use last

**Exit criteria:** Ads Operator can launch a TikTok campaign end-to-end using computer use when the API falls short. User can watch it happen on desktop.

---

## Phase 7 — Billing + Pricing (Week 9)

**Goal:** Helm takes money.

### 7.1 Helm subscription
- [ ] Stripe Billing product with three tiers per `docs/PRD.md` §7
- [ ] Sign-up flow enforces subscription before first business launch
- [ ] Tier-based limits: business count, included token budget
- [ ] Usage overage billing (metered)

### 7.2 Usage tracking
- [ ] Daily token consumption per user
- [ ] Managed Agents session-hour tracking
- [ ] Overage billing via Stripe usage-based pricing

### 7.3 Billing UI
- [ ] Current plan + usage on web settings
- [ ] Upgrade/downgrade self-serve
- [ ] Invoice history
- [ ] Payment method management (Stripe Customer Portal embedded)

### 7.4 Interchange revenue capture
- [ ] Stripe Issuing interchange set up correctly
- [ ] Revenue recognition in our accounting

**Exit criteria:** we can charge a customer, give them access, enforce tier limits, and handle churn gracefully.

---

## Phase 8 — Polish, Premium, Launch Prep (Week 10)

**Goal:** the product feels like the premium deliverable that justifies $199+/mo.

### 8.1 Motion and haptics pass
- [ ] Spring animations on every state transition
- [ ] Haptics on mobile for approvals, wins, alerts
- [ ] iOS Live Activity implemented
- [ ] "Launch theater" onboarding animation

### 8.2 Voice pass
- [ ] Mobile: hold-to-talk with live transcription
- [ ] Desktop: keyboard-triggered voice input
- [ ] Agent responses optionally spoken (system TTS, premium tier only)

### 8.3 Error states pass
- [ ] Every error has a human explanation and a suggested next step
- [ ] No raw stack traces ever visible to users
- [ ] Offline states on mobile

### 8.4 Content + copy pass
- [ ] Every piece of copy reviewed against `docs/UI_DESIGN.md` voice guidelines
- [ ] Remove every "Awesome!" and emoji from system UI
- [ ] Ensure "CEO Agent" and specialist names are used consistently (not "the AI")

### 8.5 Marketing site
- [ ] Single-page site at `helm.app` (or chosen domain)
- [ ] 60-second hero video of a real business launch
- [ ] Pricing section
- [ ] "How it works" (3 panels, not 12)
- [ ] Privacy + Terms pages (lawyer-reviewed before public launch)

### 8.6 Private beta
- [ ] Invite 50 serial entrepreneurs
- [ ] Feedback capture via in-app "Send feedback" (writes to Linear)
- [ ] Office-hours calls weekly with beta users

### 8.7 Launch readiness checklist
- [ ] Security audit (Postgres RLS, secret scanning, dep scanning)
- [ ] Load test: 100 concurrent users, 1000 agent actions/hour
- [ ] Backup and restore tested (Fly Postgres PITR)
- [ ] On-call rotation set up (PagerDuty or similar)
- [ ] Legal review of ToS, privacy policy, agent autonomy agreement
- [ ] App Store + Play Store listings ready
- [ ] Tauri signed builds distributed via auto-updater

**Exit criteria:** 50 beta users actively running businesses on Helm. We're ready for public launch.

---

## Parking Lot (Post-Launch)

Features intentionally not in the first 10 weeks, but earmarked:
- SaaS vertical support (we focus DTC at launch)
- Team/agency features
- White-label
- Native Swift + Kotlin mobile
- Custom skills marketplace
- International expansion (UK, EU, LatAm)
- Plaid for non-Stripe banking
- Enterprise tier

Revisit after public launch based on actual user demand signal.

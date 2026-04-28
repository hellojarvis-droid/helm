# ARCHITECTURE.md — Helm Technical Blueprint

## 1. The 10,000-Foot View

```
┌─────────────────────────────────────────────────────────────────────┐
│  SURFACES (3)                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Mobile (Expo)│  │ Desktop(Tauri)│  │  Web (Next.js)│             │
│  │  Dispatch UX  │  │  Computer Use │  │  Dashboard    │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └─────────────────┴──────────────────┘                      │
│                           │                                          │
│  ┌────────────────────────▼────────────────────────┐               │
│  │  API GATEWAY (FastAPI)                          │               │
│  │  /chat, /agents, /businesses, /approvals, /ws   │               │
│  └────────────────────────┬────────────────────────┘               │
│                           │                                          │
│  ┌────────────────────────▼────────────────────────┐               │
│  │  ORCHESTRATOR — CEO Agent (Claude Opus 4.7)     │               │
│  │  Persistent session per user, routes to         │               │
│  │  specialists via Managed Agents multi-agent     │               │
│  └──┬──────┬──────┬──────┬──────┬──────┬──────┬───┘               │
│     ▼      ▼      ▼      ▼      ▼      ▼      ▼                    │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                 │
│  │Idea│ │Prod│ │Creat│ │Ads │ │Soc │ │CS  │ │Fin │  (7 spec.)     │
│  │Scout│ │Bldr│ │Dir │ │Op  │ │Eng │ │    │ │/Grw│                │
│  └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘                 │
│    │      │      │      │      │      │      │                      │
│  ┌─┴──────┴──────┴──────┴──────┴──────┴──────┴────────┐            │
│  │  TOOL LAYER                                         │            │
│  │  ┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐ │            │
│  │  │ Composio │ │  Stripe │ │ Shopify│ │  Custom  │ │            │
│  │  │   MCP    │ │  MCP +  │ │  AI    │ │   MCPs   │ │            │
│  │  │  (500+)  │ │  API    │ │  Kit   │ │  (trend) │ │            │
│  │  └──────────┘ └─────────┘ └────────┘ └──────────┘ │            │
│  └─────────────────────────────────────────────────────┘            │
│                           │                                          │
│  ┌────────────────────────▼────────────────────────┐               │
│  │  WORKFLOW DURABILITY — Temporal                 │               │
│  │  (long-running business-launch workflows,       │               │
│  │  retry on failure, resume after crashes)        │               │
│  └────────────────────────┬────────────────────────┘               │
│                           │                                          │
│  ┌────────────────────────▼────────────────────────┐               │
│  │  STATE & MEMORY                                 │               │
│  │  Postgres 16   │  pgvector   │  Redis   │ S3   │               │
│  │  (relational)  │  (embeddings)│ (queues) │(blob)│               │
│  └─────────────────────────────────────────────────┘                │
│                                                                      │
│  ┌─────────────────────────────────────────────────┐               │
│  │  OBSERVABILITY                                  │               │
│  │  Langfuse (LLM)  │  Sentry  │  PostHog  │ OTel │               │
│  └─────────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Why These Choices (Defend Them Once)

- **Claude Managed Agents** (not CrewAI, not custom loop): the sandbox + state + tool execution is handled. We get to the value layer faster.
- **Composio** (not direct API per service, not building our own MCP for each): 500+ toolkits with managed OAuth, MCP-native, Claude SDK integration, SOC 2. The alternative is burning months on auth flows.
- **Stripe Issuing** (not just API + receipts): the spend-control primitives are built-in (per-auth caps, monthly caps, MCC allowlists, real-time authorization hooks). We programmatically control what agents can spend, in the authorization layer, not in our app layer.
- **Temporal** (not Celery, not homegrown queue): launching a business is a 50-step workflow that must survive process restarts, retry intelligently on third-party failures (Shopify timeouts happen), and be debuggable. Temporal is the right tool.
- **Tauri** (not Electron): 10x smaller binary, native WebView, Rust backend for the computer-use components that need to be fast. Premium feel requires the performance.
- **Expo** (not native): time to market. Plan to rewrite hot paths native by month 6.
- **Fly.io/Railway** (not AWS): we ship features, we don't architect cloud foundations. Fly gives us fast deploys, edge replicas, and Postgres in one place.

## 3. Repository Structure (Turborepo)

```
helm/
├── apps/
│   ├── api/              # Python FastAPI backend
│   ├── web/              # Next.js 15 web app
│   ├── desktop/          # Tauri desktop app
│   ├── mobile/           # Expo React Native app
│   └── workers/          # Temporal workers (Python)
├── packages/
│   ├── ui/               # Shared React components (web + desktop)
│   ├── ui-native/        # Shared React Native components
│   ├── design-tokens/    # Colors, spacing, typography (JSON)
│   ├── types/            # Shared TS types (generated from Pydantic)
│   ├── sdk-ts/           # Frontend API client (generated from OpenAPI)
│   └── agents/           # Agent definitions & system prompts (Python)
├── infra/
│   ├── migrations/       # Alembic SQL migrations
│   ├── temporal/         # Temporal workflow definitions
│   └── fly/              # Fly.io deployment configs
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── AGENTS.md
│   ├── UI_DESIGN.md
│   ├── BUILD_PLAN.md
│   └── INTEGRATIONS.md
├── config/
│   ├── composio-toolkits.json
│   └── agent-skills/
├── examples/
│   └── seed-business.py  # Scripted launch of a test business for QA
├── CLAUDE.md
├── README.md
├── package.json          # Turborepo root
├── pnpm-workspace.yaml
├── pyproject.toml        # uv workspace
└── .env.example
```

Every app and package has its own `README.md` explaining its purpose.

## 4. Backend Architecture (`apps/api`)

**Stack:**
- Python 3.12, FastAPI, Pydantic 2, uv for package management
- Claude Agent SDK (Python) for local agent dev
- Managed Agents API for production agent runs
- Composio Python SDK for tool access
- Temporal Python SDK for workflow durability
- SQLAlchemy 2.0 + Alembic for ORM + migrations
- asyncpg for Postgres
- Redis via `redis.asyncio`
- Clerk backend SDK for auth

**Key modules:**
```
apps/api/
├── helm/
│   ├── agents/
│   │   ├── orchestrator.py    # CEO Agent definition
│   │   ├── specialists/       # One file per specialist
│   │   └── skills/            # Reusable agent skills
│   ├── routes/
│   │   ├── chat.py            # SSE streaming chat
│   │   ├── businesses.py
│   │   ├── approvals.py
│   │   ├── billing.py
│   │   └── webhooks/          # Stripe, Shopify, Composio callbacks
│   ├── services/
│   │   ├── composio_client.py
│   │   ├── stripe_issuing.py
│   │   ├── shopify.py
│   │   ├── vault.py           # Ephemeral-token vault
│   │   └── kill_switch.py     # PAUSE_ALL_AGENTS logic
│   ├── models/                # SQLAlchemy + Pydantic
│   ├── workflows/             # Temporal workflows
│   ├── events/                # Event-sourced log
│   └── main.py
├── tests/
└── pyproject.toml
```

## 5. Database Schema (Core Tables)

Every table has `id: uuid`, `created_at`, `updated_at`. Every business-scoped table has `business_id`. Every user-scoped table has `user_id`. Row-level security is enforced at the ORM layer via session-scoped tenant filters.

```sql
-- Users (Clerk-sourced, cached here)
CREATE TABLE users (
  id UUID PRIMARY KEY,
  clerk_id TEXT UNIQUE NOT NULL,
  email TEXT NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('founder','operator','portfolio')),
  kill_switch_active BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Businesses (the thing agents operate on)
CREATE TABLE businesses (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  vertical TEXT NOT NULL,  -- 'dtc_physical', 'dtc_pod', 'saas', 'services'
  status TEXT NOT NULL,    -- 'initializing','active','paused','archived'
  stripe_account_id TEXT,  -- Stripe Connect account
  stripe_card_id TEXT,     -- Stripe Issuing card
  shopify_shop_domain TEXT,
  weekly_spend_cap_cents INT NOT NULL DEFAULT 50000,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON businesses(user_id);

-- Agent sessions (one per user, persistent)
CREATE TABLE agent_sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  business_id UUID REFERENCES businesses(id),  -- null for cross-business orchestrator
  managed_agent_session_id TEXT,  -- from Anthropic
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Event log (source of truth for agent actions)
CREATE TABLE agent_events (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES agent_sessions(id),
  business_id UUID REFERENCES businesses(id),
  event_type TEXT NOT NULL,  -- 'tool_call','decision','approval_requested','approval_granted','spend','error'
  agent_name TEXT NOT NULL,
  payload JSONB NOT NULL,
  cost_cents INT NOT NULL DEFAULT 0,  -- token cost
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON agent_events(session_id, created_at);
CREATE INDEX ON agent_events(business_id, created_at);

-- Approvals (what the user has to tap yes/no on)
CREATE TABLE approvals (
  id UUID PRIMARY KEY,
  business_id UUID NOT NULL REFERENCES businesses(id),
  kind TEXT NOT NULL,  -- 'spend','publish','delete','other'
  summary TEXT NOT NULL,  -- human-readable card content
  details JSONB NOT NULL,
  status TEXT NOT NULL,  -- 'pending','approved','modified','denied','expired'
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  responded_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL
);

-- Agent memory (vector store for semantic recall)
CREATE TABLE agent_memories (
  id UUID PRIMARY KEY,
  business_id UUID REFERENCES businesses(id),
  user_id UUID REFERENCES users(id),
  content TEXT NOT NULL,
  embedding VECTOR(1536),  -- pgvector
  tags TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON agent_memories USING ivfflat (embedding vector_cosine_ops);

-- Integrations (Composio connection state)
CREATE TABLE integrations (
  id UUID PRIMARY KEY,
  business_id UUID NOT NULL REFERENCES businesses(id),
  toolkit TEXT NOT NULL,  -- 'SHOPIFY','META_ADS','GOOGLE_ADS', etc.
  composio_connection_id TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ON integrations(business_id, toolkit);

-- Computer-use escalations (Phase 6 queue)
CREATE TABLE computer_use_escalations (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  business_id UUID NOT NULL REFERENCES businesses(id),
  session_id UUID NOT NULL REFERENCES agent_sessions(id),
  status TEXT NOT NULL,    -- 'queued','claimed','running','succeeded','failed','cancelled'
  requester TEXT NOT NULL, -- 'ceo_agent','ads_operator','product_builder',…
  task TEXT NOT NULL,
  app_hint TEXT NOT NULL,
  result JSONB NOT NULL DEFAULT '{}',
  error TEXT,
  claimed_by TEXT,         -- desktop device fingerprint
  claimed_at TIMESTAMPTZ,
  last_heartbeat_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON computer_use_escalations(user_id, status, created_at DESC);
CREATE INDEX ON computer_use_escalations(business_id, created_at DESC);
```

## 6. Agent Runtime — How the Orchestrator Works

The CEO Agent runs as a long-lived Claude Managed Agents session, one per user. It's created on first login and persists across device switches.

```python
# Simplified pseudocode
from anthropic import Anthropic
from composio import Composio
from claude_agent_sdk import tool, create_sdk_mcp_server

client = Anthropic()
composio = Composio()

# Define the CEO Agent
ceo_agent = client.beta.agents.create(
    name="CEO Agent",
    model="claude-opus-4-7",
    system=CEO_SYSTEM_PROMPT,  # see docs/AGENTS.md
    tools=[
        {"type": "agent_toolset_20260401"},  # bash, file, web-search
        {"type": "mcp_server", "url": COMPOSIO_MCP_URL, "auth": {...}},
        # Custom tools for dispatching to sub-agents
        delegate_to_specialist_tool,
        request_user_approval_tool,
        query_event_log_tool,
    ],
    skills=[
        "load_business_context",
        "compose_daily_digest",
        "plan_business_launch",
    ],
)

# Start a persistent session for a user
session = client.beta.sessions.create(
    agent_id=ceo_agent.id,
    environment_id=env.id,
    metadata={"user_id": user.id},
)

# Mobile/desktop/web all send messages into this same session via our API
```

**Specialist agents** are separately defined. The CEO Agent calls `delegate_to_specialist(name, task, business_id)` which spawns a short-lived child session, runs the task, and returns the result.

**Approval tool** is the critical primitive. When any agent wants to do something that hits a tier threshold, it calls `request_user_approval(summary, details)` which inserts into the `approvals` table, pushes a notification to the user's phone via APNs/FCM, and *blocks the agent session* until a response or timeout.

## 7. Computer Use Integration

For tasks without an API (e.g., TikTok doesn't have a full public ads API for small budgets, some supplier portals are web-only), the Ads Operator and Product Builder can escalate to a computer-use sub-agent:

1. The specialist calls `escalate_to_computer_use(task, app_hint)`.
2. The CEO tool path (`helm.agents.tools._escalate_to_computer_use`) and the specialist-side helper (`LLMSpecialist._handle_escalation`) both insert a row into `computer_use_escalations` with status `queued` and emit a `computer_use_requested` event.
3. The desktop app polls `GET /computer_use/queue`, atomically claims a queued row via `POST /{id}/claim` (with a stable device fingerprint), runs it through a pluggable `Executor` trait (today: `MockExecutor`; future: `AnthropicComputerUseExecutor` driving the Messages API + native screen control), heartbeats progress notes during the run, and POSTs `succeeded`/`failed` on `/{id}/complete`.
4. Stale claims (no heartbeat within `STALE_AFTER`) are lazily re-queued on read so a desktop crash doesn't strand a task.
5. If the user's desktop app is online and paired, the executor drives the user's screen and they observe the run live. If not, the row stays queued until a desktop comes online (the Helm-hosted VM fallback is reserved for a follow-up phase).

State machine: `queued → claimed → running → succeeded | failed`; any non-terminal state can transition to `cancelled` via `POST /{id}/cancel`.

**Security note:** Computer-use sessions have network-restricted sandboxes. They cannot access the Stripe card numbers directly — they pull scoped tokens from the vault for each action. The runner only ever receives `task` + `app_hint` from the API; `business_id` ownership is enforced server-side at insert time, so the model can't escalate against another tenant.

## 8. Realtime Communication

- **Mobile ↔ API:** WebSocket for chat (with SSE fallback). Push notifications for approvals.
- **Desktop ↔ API:** WebSocket, plus a local IPC bridge to the desktop app's computer-use capability.
- **Web ↔ API:** SSE for chat streams, standard REST for everything else.
- **All three stay in sync** via the backend — the chat thread is the source of truth, surfaces are views on it.

## 9. Security Model

1. **Tenant isolation** at ORM level. Every query auto-scopes to the current user's businesses. Integration tests assert cross-tenant leaks fail closed.
2. **Vault service** issues short-lived (15-min) tokens to agents. Agents never see raw API keys. Vault logs every token issuance.
3. **Spend controls** at three layers:
   - Stripe Issuing authorization webhook (real-time, can decline before charge settles)
   - Agent-level soft caps (Opus orchestrator refuses >$X actions without approval)
   - User-level daily cap (hard ceiling across all businesses)
4. **Kill switch** is a Postgres row + a Redis flag. Every agent call checks the Redis flag before any tool use. Setting it via mobile is one tap.
5. **Prompt-injection defense:** content fetched from the web (e.g., competitor scrapes) goes through a sanitizer that strips instruction-like text before reaching reasoning agents. Computer-use sandboxes are isolated from production credentials.
6. **Audit log** is append-only, cryptographically chained (hash of prev entry + current content). For compliance and for the user's own "what did the agent do?" feature.

## 10. Observability

- **Langfuse** ingests every LLM call: prompts, completions, tool calls, token costs, latency. Traces are linked to `agent_events.id` for cross-referencing.
- **Sentry** catches exceptions and performance degradation.
- **PostHog** tracks product events: business launches, approval rates, retention.
- **OpenTelemetry** spans across the FastAPI → Temporal → Managed Agents boundary for full request tracing.
- Every agent response includes a `trace_id` surfaced to the "Why?" button in the UI.

## 11. Development Environment

`docker-compose.yml` starts: Postgres, Redis, Temporal, Langfuse (self-hosted for dev). Local Claude agents run against the real Anthropic API (cost is small and it makes debugging realistic).

`pnpm dev` runs all apps in parallel via Turborepo. Hot reload works for web and mobile. Desktop requires a Tauri rebuild on Rust changes.

`pnpm test` runs the full test suite. Must pass before merge.

## 12. Deployment

- **Backend:** Fly.io, multi-region (us-east primary, us-west replica). Postgres on Fly Postgres with point-in-time recovery.
- **Web:** Vercel, connected to GitHub.
- **Desktop:** Signed builds distributed via Tauri's updater (auto-updates). macOS notarization required.
- **Mobile:** EAS (Expo Application Services) for TestFlight + Play Store Internal Testing, then store submission.
- **Temporal:** Temporal Cloud (not self-hosted). Saves ops time.

## 13. Cost Envelope (Rough, Per Active Business Per Month)

- Anthropic tokens (Opus heavy): ~$40-80
- Managed Agents session-hours: ~$20
- Composio: ~$15-30 (depends on tier)
- Stripe Issuing: $0 (interchange revenue covers it, typically net-positive)
- Shopify Basic via Partners: $29 or free on Shopify Agentic Plan (negotiate)
- Other infra (Fly, Vercel, Temporal, Langfuse): ~$10 at scale

Total marginal cost per active business: **~$100-150/mo**. Founder tier ($199) is tight; Operator ($499 for up to 5) has healthy margin; Portfolio ($1,999) is very healthy. Usage overage billing keeps heavy users profitable.

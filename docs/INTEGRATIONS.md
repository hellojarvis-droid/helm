# INTEGRATIONS.md — Composio + External Services

## 1. Why Composio

Composio gives us 500+ managed toolkits (~11,000 tools) with pre-built OAuth flows, token management, and MCP-native delivery. The alternative is burning weeks per integration building auth flows, refresh logic, rate-limit handling, and version migrations for each service. We use Composio as the default path and only build custom MCP servers when a specific need requires it.

## 2. Composio Account Setup

1. Sign up at [composio.dev](https://composio.dev)
2. Create a workspace for Helm
3. Generate a platform API key — goes in `COMPOSIO_API_KEY`
4. Enable the toolkits in §3 below

## 3. Toolkits We Enable at Launch

Each toolkit is a pre-built set of tools for a service. Store this in `config/composio-toolkits.json` so agents can reference the canonical list.

### Commerce & Product
- `SHOPIFY` — store + product management (primary commerce)
- `STRIPE` — payments + revenue (reads; we use direct API for Issuing writes)
- `PRINTFUL` — POD supplier
- `CJ_DROPSHIPPING` — physical supplier
- `ALIEXPRESS` — fallback supplier
- `AMAZON_SELLER_CENTRAL` — for cross-listing (v2)

### Marketing & Ads
- `META_ADS` — Facebook + Instagram ads
- `GOOGLE_ADS`
- `TIKTOK_ADS`
- `KLAVIYO` — email + SMS marketing
- `MAILCHIMP` — fallback email
- `GOOGLE_ANALYTICS` — analytics read

### Social (Organic)
- `INSTAGRAM`
- `TIKTOK`
- `X_TWITTER`
- `LINKEDIN`
- `THREADS`
- `YOUTUBE`
- `PINTEREST`

### Creative Generation
- `NANO_BANANA` — photorealistic image gen
- `VEO3` — video gen
- `ELEVENLABS` — voice gen for video
- `FIGMA` — design read/write

### Customer Service
- `GORGIAS` — Shopify-native CS (primary)
- `INTERCOM` — fallback
- `ZENDESK` — enterprise fallback

### Finance & Ops
- `QUICKBOOKS` — primary accounting
- `XERO` — fallback accounting
- `PLAID` — banking (non-Stripe) (v2)

### Productivity (for user workflows, not core agent tools)
- `GMAIL` — email agent
- `GOOGLE_CALENDAR`
- `SLACK` — for user-configured notifications
- `NOTION` — user's business docs
- `LINEAR` — for Helm's own issue tracking (meta)

### Domain
- `NAMECHEAP` — primary
- `GOOGLE_DOMAINS` — fallback
- `CLOUDFLARE` — DNS

### Research (for Idea Scout)
- `REDDIT`
- `WEB_SEARCH` (Composio's built-in)
- `HACKERNEWS` — SaaS trend signal
- `PRODUCT_HUNT` — launch trends

## 4. Integration Connection Flow

For every toolkit the user needs for a business:

```
User: "I want to run ads on Meta for my candle store"
↓
CEO Agent: checks integrations table — META_ADS not connected for this business
↓
CEO Agent: calls integrations.connect(business_id='...', toolkit='META_ADS')
↓
Composio returns an auth URL
↓
CEO Agent: sends approval card to user with "Connect Meta Ads" button
↓
User taps → OAuth flow on mobile → user grants permissions
↓
Composio posts webhook to our /webhooks/composio/connection-complete
↓
We write row to `integrations` table
↓
Ads Operator now has access to META_ADS toolkit for this business
```

**Key detail:** connections are per-business, not per-user. The candle store's Meta account is separate from the dog-bandana store's. Composio's `entity_id` pattern supports this — we use `{user_id}::{business_id}` as the entity ID.

## 5. Custom MCP Servers We Build Ourselves

Where Composio isn't enough, we build our own MCP servers. These live in `apps/api/helm/mcp_servers/`.

### 5.1 `trend_data_mcp` — Proprietary Trend Intelligence

Composio has Reddit and social toolkits but doesn't give us aggregated trend intelligence. This MCP is a moat — it's the "proven demand" signal for Idea Scout.

**Data sources:**
- TikTok hashtag velocity (scraped via TikTok Creative Center public API)
- Reddit discussion volume by product category (via Pushshift or our own crawl)
- Amazon BSR movers (scraped daily)
- Meta Ad Library density (public API)
- Google Trends (pytrends)

**Tools exposed:**
- `get_trend_score(category: str) -> TrendScore`
- `find_rising_products(vertical: str, min_score: float) -> list[Product]`
- `competitor_ad_density(category: str, platform: str) -> int`

Runs as a background crawler + FastAPI service. Postgres-backed with pgvector for similarity search across product concepts.

### 5.2 `stripe_issuing_mcp`

We don't use Composio's Stripe toolkit for Issuing because it's a sensitive control surface where we want direct, auditable integration. This is an MCP wrapper around the Stripe Issuing API with tenant-scoped access.

**Tools exposed:**
- `create_card_for_business(business_id)`
- `update_spending_controls(card_id, controls)`
- `authorize_transaction(business_id, amount, merchant)` — for the real-time auth hook
- `get_card_activity(business_id, timeframe)`

### 5.3 `policy_templates_mcp`

Vetted, lawyer-reviewed policy templates for common business setups. Shopify shipping policy, ToS, privacy, returns, data processing for different geographies.

### 5.4 `shopify_direct_mcp` (possibly)

If Composio's Shopify toolkit isn't high-fidelity enough for agentic storefronts (UCP-specific features, Agentic Plan configuration), we wrap the Shopify Admin API via Shopify's own AI Toolkit MCP directly.

Decision point: evaluate Composio's SHOPIFY toolkit in Phase 1. If it covers our needs, don't build this. If not, build.

## 6. External Service Setup Checklist

### Stripe (Platform + Issuing for Agents)
1. Apply at [stripe.com/issuing](https://stripe.com/issuing) — specifically request **Issuing for Agents** access (it's a separate program with specific underwriting)
2. Register as a Connect platform
3. Configure Treasury for platforms (US only at launch)
4. Webhook endpoint: `/webhooks/stripe`
5. Test mode first, production after real revenue

### Shopify (Partners + Agentic Plan)
1. Join [Shopify Partners](https://partners.shopify.com)
2. Apply for the **Shopify Agentic Plan** — this gives us AI-channel syndication (ChatGPT, Copilot, Google) + partner pricing for merchants
3. Register a custom Shopify app for Helm (OAuth scope: write_products, write_orders, write_customers, read_reports, write_payments, write_marketing_events)
4. Install Shopify AI Toolkit MCP server
5. OAuth installed per business

### Anthropic
1. API access with `managed-agents-2026-04-01` beta header
2. Request access to multi-agent coordination (it's in research preview)
3. Set organization-level spend limits as a safety net
4. Langfuse integration for trace capture

### Meta (Facebook + Instagram)
1. Meta Business SDK access
2. Register as a Marketing API partner (advanced access required to create ad accounts programmatically)
3. Business Manager structure: Helm as the top-level BM, each user's businesses as child BMs (recommended by Meta for agency-like operations)
4. Rate limit: stay under the ad-account-creation limits by pacing new business launches

### Google Ads
1. Google Ads API developer token
2. Manager Account (MCC) structure
3. OAuth scope: `https://www.googleapis.com/auth/adwords`

### TikTok Business
1. TikTok Ads Marketing API access
2. TikTok Business Center registration
3. Fallback to computer-use for flows that don't have API coverage

## 7. Ephemeral Token Vault

Every agent tool call against a service follows this pattern:

```python
async def call_composio_tool(
    user_id: UUID,
    business_id: UUID,
    toolkit: str,
    tool: str,
    params: dict,
) -> dict:
    # 1. Verify kill switch
    await kill_switch.assert_active_not_set(user_id)

    # 2. Verify tenant access
    integration = await db.get_integration(business_id, toolkit)
    if not integration:
        raise IntegrationNotConnected(toolkit)

    # 3. Fetch ephemeral token from vault
    token = await vault.get_token(
        integration.composio_connection_id,
        ttl_seconds=900,  # 15 min
    )

    # 4. Execute via Composio with the scoped token
    result = await composio_client.execute(
        tool=tool,
        params=params,
        auth_token=token,
    )

    # 5. Log to event log
    await event_log.write(
        business_id=business_id,
        event_type='tool_call',
        payload={'toolkit': toolkit, 'tool': tool, 'result_summary': summarize(result)},
    )

    return result
```

The vault service (`services/vault.py`) is the only module that sees raw credentials. Agents never touch them.

## 8. Rate Limits We Plan For

- **Meta Ads API:** 200 calls per user per hour. We batch and cache.
- **Google Ads API:** 15,000 operations per day per MCC. Fine at our scale.
- **TikTok Ads:** 300 calls per minute. We pace.
- **Shopify:** 2 calls per second per store. Plenty.
- **Composio:** their platform limits depend on tier. Start on their Scale plan.
- **Anthropic:** tier-based, typically 50 requests per minute on the Managed Agents API. Plan ahead for scaling.

Rate-limit handling is in `services/rate_limiter.py` with per-toolkit policies.

## 9. Webhooks We Receive

- `POST /webhooks/stripe` — payment events, issuing auth events
- `POST /webhooks/shopify/{shop}` — order events, product events
- `POST /webhooks/composio` — connection events, async tool-call completions
- `POST /webhooks/meta` — ad account events, creative rejections
- Clerk webhooks for user lifecycle

All webhook handlers verify signatures and are idempotent by event ID.

## 10. Fallback Strategy

When Composio has an outage or a toolkit returns errors:

1. Agent retries with exponential backoff (3 attempts, 1s/4s/15s)
2. If still failing, fallback path:
   - For reads: use cached data with a staleness warning
   - For writes: queue the action, notify the user, retry when service recovers
3. Critical paths (Stripe, primary Shopify) bypass Composio entirely with direct integration

## 11. Cost Management

Composio billing is usage-based. Monitor closely in `apps/api/helm/services/cost_tracking.py`. Budget alert at 80% of monthly ceiling. Self-throttle at 95%.

Anthropic spend is the bigger line item. Set organization-level spend limits as a hard cap.

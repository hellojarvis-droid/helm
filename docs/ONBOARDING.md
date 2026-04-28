# ONBOARDING.md — go-live checklist

The codebase is feature-complete. This is what's left for the human (you, the
operator) to do before the product can take real money from real users. Items
are ordered by dependency: each step's prereqs are above it.

DEPLOY.md covers Phase 0 staging setup. This document covers everything
between staging-green and public launch.

---

## 1. External accounts to create (60–90 minutes total)

- [ ] **Apple Developer account** — $99/yr — https://developer.apple.com/programs/
  needed for: TestFlight + App Store + APNs push certificate
- [ ] **Google Play Developer** — $25 one-time — https://play.google.com/console
  needed for: Play Store internal track + FCM push
- [ ] **Expo account + project** — free — https://expo.dev
  needed for: EAS builds, Expo Push Notifications service auth
- [ ] **Apple Push Notification cert** — generated inside the Apple Developer
  console; upload to Expo so EAS can sign push payloads.
  https://docs.expo.dev/push-notifications/push-notifications-setup/
- [ ] **Stripe live mode activation** — fill in business details + bank account
  in Stripe dashboard. https://dashboard.stripe.com/account/onboarding
- [ ] **Stripe Issuing application** — apply for production Issuing
  (test mode is on by default; production needs review).
  https://dashboard.stripe.com/issuing/onboarding
- [ ] **Composio production workspace** — upgrade from free tier (free is
  capped at 2 projects). https://app.composio.dev/billing
- [ ] **Anthropic + OpenAI** — production API keys (separate from any test
  keys). Set spend caps in each console.
- [ ] **Langfuse Cloud project** — free tier — https://cloud.langfuse.com
- [ ] **PostHog Cloud project** — free tier — https://us.posthog.com
- [ ] **Sentry org + projects** (api, web, mobile) — free tier
  https://sentry.io
- [ ] **Vercel account** + import the GitHub repo — free tier covers staging
  https://vercel.com/new
- [ ] **Domain** — pick + buy. Suggested registrar: Namecheap, Porkbun,
  Cloudflare. Point it at Vercel + Render once both are live.

## 2. Stripe products + prices (15 minutes)

Code already supports three tiers. Create matching prices in Stripe Dashboard:

- [ ] **Founder** — $199/month recurring
- [ ] **Operator** — $499/month recurring
- [ ] **Portfolio** — custom (no public price; sales-led)
- [ ] **Metered overage** — usage-based price in cents, billed monthly. The
  `services/usage_reporter.py` posts `quantity=cost_cents` so set `unit
  amount` to $0.01 and enable graduated tiers if you want a free monthly
  allowance.

Copy the four price IDs into Render env:
```
STRIPE_PRICE_FOUNDER=price_xxx
STRIPE_PRICE_OPERATOR=price_xxx
STRIPE_PRICE_PORTFOLIO=price_xxx   # optional; portfolio is currently mailto:
```

## 3. Stripe Customer Portal config (5 min)

Customer Portal needs to be turned on once. Dashboard → Settings → Billing →
Customer Portal. Enable: payment method, plan switch, cancel, invoice
history. Set the post-cancellation return URL to `https://helm.app/billing`
(or your domain).

## 4. Stripe webhook (5 min)

In Dashboard → Developers → Webhooks → Add endpoint:
- URL: `https://api.helm.app/webhooks/stripe`
- Events to send:
  - `account.updated` (Connect onboarding)
  - `issuing_authorization.request` (live spend decisions)
  - `payment_intent.succeeded` (revenue)
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`

Copy the signing secret into Render env as `STRIPE_WEBHOOK_SECRET`.

## 5. Composio webhook (5 min)

Dashboard → Webhooks → Add. URL `https://api.helm.app/webhooks/composio`,
signing secret to `COMPOSIO_WEBHOOK_SECRET`.

## 6. EAS / mobile build setup (~30 min)

```bash
npm i -g eas-cli
cd apps/mobile
eas login        # uses your Expo account
eas init         # creates the EAS project, writes the projectId into app.json
eas credentials  # generate iOS push key + provisioning profile, Android
                 # upload key. EAS handles APNs cert + Play upload key.
eas build --profile preview --platform all
```

The `expo-application` projectId pickup in `lib/push.ts` already reads
`Constants.expoConfig.extra.eas.projectId` so push tokens generate
correctly once `eas init` writes the id.

For TestFlight + Play internal track:
- [ ] `eas submit --platform ios` (after first successful production build)
- [ ] `eas submit --platform android`

## 7. Tauri code signing — ~$300/yr + manual (deferred unless launching desktop today)

Tauri release builds need:
- macOS: Apple Developer cert (covered by step 1) + notarization. Tauri's
  `signingIdentity` config + `notarize` action.
- Windows: EV Code Signing certificate from DigiCert / Sectigo (~$300/yr).
- Linux: no signing required, AppImage works as-is.

Helm's desktop is currently a development-only artifact (Session 43). The
shell loads the deployed web app — it's safe to ship without signing for
internal use. Skip until customer demand surfaces.

## 8. Render production env vars (10 min)

In Render Dashboard → helm-api → Environment, set:

```
# Already set per DEPLOY.md
DATABASE_URL=…
SUPABASE_URL=…
SUPABASE_ANON_KEY=…
SUPABASE_SERVICE_ROLE_KEY=…

# New for production
ANTHROPIC_API_KEY=sk-ant-…       # production, not test
COMPOSIO_API_KEY=ck_…             # production workspace
COMPOSIO_WEBHOOK_SECRET=…         # from step 5

STRIPE_SECRET_KEY=sk_live_…       # flip from sk_test_
STRIPE_WEBHOOK_SECRET=whsec_…     # from step 4
STRIPE_ISSUING_ENABLED=true       # only after step 1's Issuing approval
STRIPE_PRICE_FOUNDER=price_…      # from step 2
STRIPE_PRICE_OPERATOR=price_…
STRIPE_PRICE_PORTFOLIO=price_…
BILLING_SUCCESS_URL=https://helm.app/billing?status=success
BILLING_CANCEL_URL=https://helm.app/billing?status=cancel

OPENAI_API_KEY=sk-…               # for /chat/transcribe (Whisper)

SENTRY_DSN=…                      # API project DSN
LANGFUSE_PUBLIC_KEY=pk_…
LANGFUSE_SECRET_KEY=sk_…

EXPO_ACCESS_TOKEN=…               # optional; Enhanced Security push auth
WEB_ORIGIN_ALLOWLIST=https://helm.app,https://www.helm.app
```

Render auto-deploys on env-var change.

## 9. Vercel production env vars (5 min)

Project → Settings → Environment Variables. Set for "Production":

```
NEXT_PUBLIC_SUPABASE_URL=…
NEXT_PUBLIC_SUPABASE_ANON_KEY=…
NEXT_PUBLIC_HELM_API_BASE=https://api.helm.app

NEXT_PUBLIC_SENTRY_DSN=…          # web project DSN
NEXT_PUBLIC_SENTRY_ENV=production
SENTRY_ORG=…
SENTRY_PROJECT=helm-web
SENTRY_AUTH_TOKEN=…               # for source-map upload at build

NEXT_PUBLIC_POSTHOG_KEY=phc_…
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
```

## 10. Mobile env via EAS secrets (5 min)

```bash
cd apps/mobile
eas secret:create --scope project --name EXPO_PUBLIC_HELM_API_BASE --value https://api.helm.app
eas secret:create --scope project --name EXPO_PUBLIC_SUPABASE_URL --value https://…
eas secret:create --scope project --name EXPO_PUBLIC_SUPABASE_ANON_KEY --value …
eas secret:create --scope project --name EXPO_PUBLIC_SENTRY_DSN --value …
eas secret:create --scope project --name EXPO_PUBLIC_POSTHOG_KEY --value phc_…
```

## 11. Production-grade additions you may want before public launch

- [ ] **Rate limiting** — currently no per-user rate limit on /chat or
  /transcribe. Cheapest fix: Cloudflare in front of Render with a route
  rule. Software fix: add `slowapi` or a custom Redis token bucket.
- [ ] **Database backups verified** — Supabase does PITR on Pro+ tier.
  Restore once into a fresh project to confirm the runbook works.
- [ ] **Load test** — `scripts/load-test.k6.js` shipped with the repo; run
  `k6 run scripts/load-test.k6.js` from a network-close VPS, target 100
  concurrent users, 1000 chat turns/hour.
- [ ] **Penetration test** — third-party. Cure53, NCC Group, or boutique.
  $5k–$15k for a 5-day engagement on this surface.
- [ ] **Static security scanning** — CodeQL needs GitHub Advanced Security
  ($49/active-committer/mo) to upload SARIF on private repos, so we don't
  ship a `.github/workflows/codeql.yml` by default. When you enable GHAS
  (Settings → Code security and analysis), commit the standard CodeQL
  workflow and it'll just work. Free alternative for now: Trivy filesystem
  scan in CI (`trivy fs --severity HIGH,CRITICAL .`) — catches CVEs in
  pinned deps but not custom code paths.
- [ ] **Lawyer-reviewed Terms + Privacy** — the placeholder /terms and
  /privacy pages need replacement before paid signups. Local DTC ecommerce
  + AI agents is a nuanced area — find a lawyer who knows both.
- [ ] **Insurance** — Cyber + E&O at minimum. Vouch and Coalition both
  underwrite this profile in 24h.

## 12. Phase 6 Computer Use

The Phase 6 queue + state machine is shipped. Specifically:

- `escalate_to_computer_use` (CEO tool) and `LLMSpecialist._handle_escalation`
  (used by Ads Operator + Product Builder) both insert rows into
  `computer_use_escalations` with status `queued`.
- The desktop app (Tauri) ships a polling runner (`apps/desktop/src-tauri/src/runner.rs`)
  that calls `GET /computer_use/queue`, atomically claims a row, heartbeats
  while running, and POSTs a terminal state on completion.
- The runner's `Executor` trait is pluggable. Today it ships with `MockExecutor`
  (sleeps, reports success) so the queue/claim/heartbeat/complete pipeline
  can be exercised end-to-end without screen control.

**Remaining work** to make computer-use actually run real tasks:
- Implement `AnthropicComputerUseExecutor` against the Messages API
  computer-use tool — drives the user's screen via native input/screen-capture
  primitives. ~1–2 sessions of work + per-OS testing.
- Optional: a Helm-hosted sandbox fallback for users without the desktop
  app installed (Anthropic-provided VM when available; self-hosted Xvfb +
  Chromium otherwise). Reserved for a later phase based on demand signal.

The 8 specialists cover ~95% of legitimate workflows via Composio APIs;
the remaining 5% (TikTok small-budget self-serve, supplier portals
without Composio coverage) is what computer-use unlocks.

## 13. What's done — for handoff confidence

Per BUILD_PLAN.md phases:
- Phase 0 — ✅
- Phase 1 — ✅ (CEO + 8 real specialists, event log, kill switch, /chat SSE)
- Phase 2 — ✅ (Stripe Connect + Issuing + decide_authorization + revenue)
- Phase 3 — ✅ (Shopify/Printful via Composio; Product Builder is real)
- Phase 4 — ✅ for mobile + web; Tauri shell scaffolded for desktop
- Phase 5 — ✅ (all 8 specialists are LLMSpecialists, no stubs)
- Phase 6 — interface scaffolded; sandbox is operational work above
- Phase 7 — ✅ (tier limits + Checkout + Portal + metered)
- Phase 8 — landing + pricing + terms + privacy + error boundaries +
  CSP + dark mode shipped; LiveActivity, App Store listings, marketing
  video, beta-user invites are operational work above

CI gates on every push: `pnpm format:check`, `pnpm typecheck`,
`pnpm --filter @helm/web build`, `uv run pytest` against pgvector/pg16.

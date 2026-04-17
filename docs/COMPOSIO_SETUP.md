# Composio setup — one-time dashboard steps

Helm's integrations layer uses Composio as the unified OAuth gateway. To
test the OAuth flow end-to-end you need to do a few clicks in Composio's
dashboard — this guide tells you which ones.

## 1. Confirm your Composio project + API key

- Open https://app.composio.dev
- Confirm you're signed in with the account the `COMPOSIO_API_KEY` in
  `.env.local` (and Render env) belongs to.
- At top-right you should see a "default" or project-name dropdown — the
  API key is scoped to one project.

## 2. Enable the Gmail toolkit (our first smoke test)

- Dashboard → **Toolkits** (or "Apps") → search **Gmail** → click it.
- Click **Enable** / **Add to project** if it's not already enabled.
- Composio provides managed OAuth for Gmail by default — you do NOT need
  to bring your own Google OAuth client for the smoke test.

## 3. (Optional for Session 4 — required for Session 5) Webhook callback URL

Session 4 uses poll-based confirmation: after you complete OAuth, the
client calls `POST /integrations/{id}/sync` which pulls the status from
Composio. That works without any webhook setup.

For Session 5 we'll flip to webhook-driven updates. When you're ready:

- Dashboard → **Settings** → **Webhooks**
- Add endpoint: `https://helm-api-ux69.onrender.com/webhooks/composio`
- Copy the signing secret
- In Render dashboard, set `COMPOSIO_WEBHOOK_SECRET=<the secret>` on
  `helm-api` → Environment
- Redeploy

Not required for the Session 4 test.

## 4. Smoke-test the Gmail OAuth flow (end-to-end)

**Prerequisite:** You'll need a Supabase JWT for yourself. Easiest way:
sign in to your Supabase project's Studio → any table view → browser
DevTools → Application → Local Storage → copy the `access_token`.

Then, from your Mac:

```bash
export HELM_API="https://helm-api-ux69.onrender.com"
export JWT="<paste your Supabase access_token>"

# 1. Create a business.
BIZ=$(curl -s -X POST "$HELM_API/businesses" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Composio Test","vertical":"dtc_physical"}' | jq -r .id)
echo "business: $BIZ"

# 2. Initiate the Gmail OAuth flow.
RESP=$(curl -s -X POST "$HELM_API/integrations/$BIZ/connect/gmail" \
  -H "Authorization: Bearer $JWT")
echo "$RESP" | jq .
REDIRECT=$(echo "$RESP" | jq -r .redirect_url)
INTEG_ID=$(echo "$RESP" | jq -r .integration_id)

# 3. Open the redirect URL and grant access to Gmail.
open "$REDIRECT"

# 4. After granting, poll sync until status=active.
curl -s -X POST "$HELM_API/integrations/$INTEG_ID/sync" \
  -H "Authorization: Bearer $JWT" | jq .
```

Expected final JSON: `{"status": "active", "toolkit": "gmail", ...}`.

If that happens, Composio wiring is real. Session 5 builds the first
Composio-backed specialist on top (most likely an email-capable agent or
Gmail-triggered Social Engagement inbox).

## Troubleshooting

- **502 "Composio did not return a redirect URL"** — the toolkit isn't
  enabled in your Composio project. Go back to step 2.
- **409 on connect** — an active connection already exists for this
  (business, toolkit). Fine; you don't need to reconnect.
- **sync returns status=pending indefinitely** — OAuth wasn't completed.
  Re-open the redirect URL from the connect response.
- **No "connect your Gmail" screen in the redirect** — some Composio
  managed auth flows error out with a workspace-level OAuth config
  missing. Reach out to Composio support or open the toolkit settings
  and set up a custom Google OAuth app.

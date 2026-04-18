# WEB_SETUP.md — Deploying apps/web to Vercel

## Local dev

```bash
# From repo root
pnpm install

# Create apps/web/.env.local:
cat > apps/web/.env.local <<EOF
NEXT_PUBLIC_SUPABASE_URL=https://<your-supabase-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase anon key>
NEXT_PUBLIC_HELM_API_BASE=http://localhost:8000
EOF

# Terminal 1: the API
pnpm api:dev

# Terminal 2: the web app
pnpm web:dev
# → http://localhost:3000
```

Sign up on `/sign-in` with any email+password. You're in.

## Deploying to Vercel (one-time)

1. Go to https://vercel.com/new, import the `hellojarvis-droid/helm` GitHub repo.
2. **Root Directory**: `apps/web` (Vercel auto-detects Next.js).
3. **Build Command**: leave blank (Vercel defaults to `next build`).
4. **Environment Variables** — add these three:
   - `NEXT_PUBLIC_SUPABASE_URL` — your Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase anon key
   - `NEXT_PUBLIC_HELM_API_BASE` — `https://helm-api-ux69.onrender.com` (your Render API URL)
5. Click **Deploy**. Vercel watches `main` and auto-deploys on push.

## Cross-origin note

The API is on `helm-api-ux69.onrender.com`; the web is on `<vercel-subdomain>.vercel.app`.
Browser calls from web → API will be cross-origin. FastAPI doesn't enable CORS
by default and the API doesn't allow cross-origin calls yet — we'll wire
`CORSMiddleware` with an allowlist pointing at the Vercel domain in Session 9.

Local dev avoids this via a Next.js rewrite (`/api/*` → `http://localhost:8000/*`).

## Sanity check after deploying

```bash
curl https://<your-vercel-domain>.vercel.app           # 307 redirect to /sign-in
curl -I https://<your-vercel-domain>.vercel.app/chat   # 307 redirect to /sign-in?next=/chat
```

Both redirects mean the middleware is evaluating correctly.

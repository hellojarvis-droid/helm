# @helm/web

Next.js 15 App Router + Tailwind 3 + Supabase Auth. The web surface of the
three-surface Helm product.

## Local dev

```bash
# From repo root:
pnpm install

# Create apps/web/.env.local with:
# NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
# NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
# NEXT_PUBLIC_HELM_API_BASE=http://localhost:8000   # or the Render URL

pnpm --filter @helm/web dev
# → http://localhost:3000
```

For the API backend, run `pnpm api:dev` from repo root in a second terminal.

## Auth flow

- `middleware.ts` rotates the Supabase session cookie on every request.
- `/sign-in` handles both sign-in and sign-up via email+password.
- Protected routes (`/chat`, `/businesses`) redirect to `/sign-in` when no session.
- The client reads the JWT from the Supabase browser client and attaches it
  as `Authorization: Bearer <token>` to every Helm API call.

## Routes

| Path              | Notes                                                 |
| ----------------- | ----------------------------------------------------- |
| `/`               | Server-side redirect to `/chat` or `/sign-in`         |
| `/sign-in`        | Email + password (also sign-up toggle)                |
| `/chat`           | CEO Agent conversation; streams SSE from `POST /chat` |
| `/businesses`     | List + drilldown                                      |
| `/businesses/new` | Create form (name, vertical, weekly cap slider)       |

## Deploying to Vercel

See `docs/WEB_SETUP.md` at the repo root.

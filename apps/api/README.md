# helm-api

The FastAPI backend. Orchestrates the CEO Agent, speaks to Composio + Stripe + Shopify, serves the chat API to all three surfaces.

## Structure

```
apps/api/
├── helm/
│   ├── main.py            # FastAPI app factory + lifespan
│   ├── config.py          # Pydantic settings (env-backed)
│   ├── logging.py         # structlog config
│   ├── middleware.py      # CorrelationIdMiddleware
│   ├── auth.py            # Supabase JWT validation + CurrentUser
│   ├── routes/
│   │   ├── health.py      # GET /health
│   │   └── auth.py        # POST /auth/sync
│   ├── db/
│   │   ├── models.py      # SQLAlchemy 2.0 models (core schema)
│   │   ├── session.py     # async engine + session factory
│   │   └── tenant.py      # tenant-scoped query helpers
│   └── services/
│       └── user_sync.py   # upsert user on first login
├── alembic/               # migrations (env.py + versions/)
├── tests/                 # pytest
├── Dockerfile
└── pyproject.toml
```

## Conventions

- `mypy --strict` on `helm/`. No `Any` without a comment explaining why.
- `ruff` for format + lint.
- Every DB-touching helper takes an `AsyncSession` — do not open sessions inside helpers.
- Every agent-touching helper takes the tenant context explicitly. No global tenant state.
- Tests use a real Supabase-compatible Postgres (Supabase local or a test project). SQLite is only used for schema-agnostic smoke tests because pgvector/JSONB don't translate.

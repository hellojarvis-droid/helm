# infra/

Deploy configs and long-lived infra glue.

Current:

- `../render.yaml` — Render Blueprint (at repo root so Render discovers it)
- Temporal workflow definitions land here in Phase 1
- Migrations live in `apps/api/alembic` (keeps schema + migrations colocated with the ORM)

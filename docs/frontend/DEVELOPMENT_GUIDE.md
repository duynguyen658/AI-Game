# Frontend Development Guide

Requirements are Node.js 22 and pnpm 11. Start PostgreSQL, API, and worker from the repository root, then start Next.js:

```bash
docker compose up -d postgres
alembic upgrade head
python -m app.demo_seed
uvicorn app.main:app --reload
python -m app.workers.main
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:3000`. Development may use `BACKEND_API_URL=http://127.0.0.1:8000`. Demo sessions require `AUTH_MODE=demo`, `DEMO_AUTH_ENABLED=true`, and a strong `SESSION_SECRET`. Production uses `AUTH_MODE=oidc`; it never accepts a browser-selected identity or role.

OIDC development can use cookie storage only for focused local work. Set `OIDC_SESSION_STORAGE=cookie`, `OIDC_SESSION_ENCRYPTION_KEY` to at least 32 characters, and retain `AUTH_COOKIE_MAX_BYTES=3800`; oversized payloads fail rather than truncate. Multi-replica and production runs must use PostgreSQL storage with `FRONTEND_DATABASE_URL`. The deterministic issuer is enabled only with `OIDC_TEST_ISSUER_ENABLED=true` outside production.

Regenerate the API contract with `python -m scripts.export_openapi`, then run `pnpm openapi:generate` and `pnpm openapi:check`. Add data access through `lib/api`, preserve backend status enums, and provide loading, empty, error, and permission states for each new surface.

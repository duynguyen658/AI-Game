# Frontend Development Guide

Requirements are Node.js 22 and pnpm 11. Start PostgreSQL, API, and worker from the repository root, then start Next.js:

```bash
docker compose up -d postgres
alembic upgrade head
python -m app.cli.seed_m7_demo
uvicorn app.main:app --reload
python -m app.workers.main
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:3000`. The default BFF target is `http://localhost:8000`; override `BACKEND_BASE_URL` for another API. Demo sessions require `DEMO_AUTH_ENABLED=true`. Production mode also requires a strong `DEMO_SESSION_SECRET` until SSO replaces the demo adapter.

Run `pnpm openapi:generate` only after intentionally regenerating `openapi.m8.json` from FastAPI. Run `pnpm openapi:check` before committing. Add data access through `lib/api`, preserve backend status enums, and provide loading, empty, error, and permission states for each new surface.

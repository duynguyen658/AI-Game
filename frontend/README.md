# Cyber Legends Frontend

Next.js App Router workspace for M8 Frontend Productization. It provides Applied AI task workflows, human approval, prompt/provider management, business-impact analytics, and production operations views over the FastAPI backend.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

The local app opens at `http://localhost:3000` and proxies backend requests to `BACKEND_BASE_URL` (default `http://localhost:8000`). Demo login is controlled by `DEMO_AUTH_ENABLED`; production mode requires `DEMO_SESSION_SECRET`.

Quality gates:

```bash
pnpm openapi:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

Architecture, testing, deployment, accessibility, design-system, and demo documentation live in `../docs/frontend/`.

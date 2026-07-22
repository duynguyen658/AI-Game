# Cyber Legends Frontend

Next.js App Router workspace for M8 Frontend Productization. It provides Applied AI task workflows, human approval, prompt/provider management, business-impact analytics, and production operations views over the FastAPI backend.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

The local app opens at `http://localhost:3000`. Server-side BFF requests use `BACKEND_API_URL`; localhost is only the development default. Demo login requires `AUTH_MODE=demo`, `DEMO_AUTH_ENABLED=true`, `ALLOW_PRODUCTION_DEMO=true` for a production-built local image, and `SESSION_SECRET`. Production uses `AUTH_MODE=oidc`, an encrypted HttpOnly session, and server-side Bearer forwarding. Browser-selected identities are never used in OIDC mode.

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

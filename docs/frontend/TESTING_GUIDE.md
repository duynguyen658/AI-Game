# Frontend Testing Guide

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

Authentication-focused tests run with `pnpm test:auth`. With migrated PostgreSQL, set `RUN_POSTGRES_OIDC_TESTS=1` and `FRONTEND_DATABASE_URL` to include opaque-cookie, encrypted-row, refresh-claim, compare-and-swap, revocation, and cleanup coverage. Cookie fixtures report byte counts only; token values are never printed.

Vitest uses jsdom and React Testing Library. Playwright smoke tests start the production Next.js standalone server, create an encrypted demo session, mock only backend responses, and exercise desktop, tablet, and mobile layouts. Axe runs with color contrast enabled. Nine deterministic visual baselines cover login, dashboard, campaign, CSV, document, media, prompt experiment, business impact, and jobs.

`docker-compose.demo.yml` supplies PostgreSQL, migrations, deterministic seed data, FastAPI, worker, shared media storage, and frontend. The full-stack Playwright suite crosses the real BFF and database for campaign approval/IDOR, CSV and document uploads, feedback, prompt experiments, partial provider comparisons, image approval/rejection, storyboards, job retry, alerts, and health. `DEMO_PROVIDER_ALIASES=true` maps named comparison providers to deterministic clients only in demo; production rejects this flag.

CI never contacts a real model or image provider. Backend regression tests run with mock providers and PostgreSQL. Failure artifacts contain the Playwright HTML report, traces, and failure screenshots. Manual release verification follows `DEMO_SCRIPT.md` against the seeded API and worker.

The `production-auth` CI job starts PostgreSQL, FastAPI, Next.js, and `scripts/test-oidc-issuer.mjs`. It deterministically validates login, PKCE/state/nonce, Bearer forwarding, post-expiry refresh, refresh-token rotation, logout, and revoked-session denial. The test issuer never contacts an external identity provider and production configuration rejects its enable flag.

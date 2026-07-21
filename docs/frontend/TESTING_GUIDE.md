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

Vitest uses jsdom and React Testing Library. Playwright smoke tests start the production Next.js standalone server, create an encrypted demo session, mock only backend responses, and exercise desktop, tablet, and mobile layouts. Axe runs with color contrast enabled. Nine deterministic visual baselines cover login, dashboard, campaign, CSV, document, media, prompt experiment, business impact, and jobs.

`docker-compose.demo.yml` supplies PostgreSQL, migrations, deterministic seed data, FastAPI, worker, shared media storage, and frontend. The full-stack Playwright suite crosses the real BFF and database for campaign approval/IDOR, CSV and document uploads, feedback, prompt experiments, partial provider comparisons, image approval/rejection, storyboards, job retry, alerts, and health. `DEMO_PROVIDER_ALIASES=true` maps named comparison providers to deterministic clients only in demo; production rejects this flag.

CI never contacts a real model or image provider. Backend regression tests run with mock providers and PostgreSQL. Failure artifacts contain the Playwright HTML report, traces, and failure screenshots. Manual release verification follows `DEMO_SCRIPT.md` against the seeded API and worker.

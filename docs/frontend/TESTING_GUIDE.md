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

Vitest uses jsdom and React Testing Library. MSW intercepts the BFF boundary so API normalization, correlation IDs, and form invariants are deterministic. Playwright starts Next.js, creates a real signed demo session, mocks only backend network responses, checks core routes, and runs an axe smoke check.

CI never contacts a real model or image provider. Backend regression tests run with mock providers and PostgreSQL. Failure artifacts contain the Playwright HTML report, traces, and failure screenshots. Manual release verification follows `DEMO_SCRIPT.md` against the seeded API and worker.

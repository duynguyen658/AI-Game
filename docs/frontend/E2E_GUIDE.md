# M8 End-to-End Guide

Mocked Playwright tests validate UI states, desktop/mobile/tablet layout, keyboard focus, Axe including color contrast, and nine committed visual baselines. They do not count as backend coverage.

The deterministic full-stack suite starts PostgreSQL, migrations, demo seed, FastAPI, worker, and the production Next.js image:

```bash
docker compose -f docker-compose.demo.yml up -d --build
cd frontend
E2E_FULL_STACK=1 PLAYWRIGHT_EXTERNAL_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
  pnpm exec playwright test e2e/full-stack.spec.ts --project=chromium
cd ..
docker compose -f docker-compose.demo.yml down -v
```

The suite logs in through the real frontend and calls FastAPI only through the BFF. It covers campaign execution and approval, cross-user campaign/workflow/job/timeline/media denial, manager override, CSV/document upload and feedback, prompt experiment execution, successful plus partial provider comparison results, image approval/rejection, storyboard generation, failed-job retry, alert acknowledgement, health, and business impact. API and worker share the demo media volume. Provider aliases are explicit deterministic demo fixtures; no external provider credentials are used.

CI uploads Playwright diagnostics on failure and always emits Compose logs before teardown. Never report full-stack E2E as passing from the mocked workspace suite alone.

The OIDC browser gate is separate from demo E2E. It starts the local issuer on port `43132`, API on `8000`, and frontend on `43131`, then runs `E2E_OIDC=1 PLAYWRIGHT_EXTERNAL_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:43131 pnpm test:e2e:oidc`. Access tokens last two seconds and Playwright uses bounded polling until a protected BFF request records one refresh and one rotation. It then logs out and confirms the same protected route returns 401. No arbitrary long sleep or external provider is used.

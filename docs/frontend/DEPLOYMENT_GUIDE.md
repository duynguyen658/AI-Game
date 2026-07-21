# Frontend Deployment Guide

The production image is multi-stage, uses Next standalone output, and runs as the unprivileged `nextjs` user. Build and start the full stack with:

```bash
docker compose -f docker-compose.production.yml up --build
```

Required deployment values include PostgreSQL credentials, backend secrets already documented by M6/M7, `DEMO_SESSION_SECRET`, and the public frontend port. Inside Compose, `BACKEND_BASE_URL=http://api:8000`. Do not expose that internal address as a public browser variable.

The container health check requests `/login`. API readiness remains separately enforced by the API container. Terminate TLS at the ingress, replace demo authentication with SSO before external access, rotate secrets through the deployment platform, and keep real provider keys only in API/worker environments.

Rollback is image based. Database downgrade is not implied by a frontend rollback. Confirm OpenAPI compatibility, API readiness, worker freshness, queue depth, and the login/dashboard smoke before shifting traffic.

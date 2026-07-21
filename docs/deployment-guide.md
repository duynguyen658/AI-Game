# Deployment Guide

## Build and Start

```bash
docker build -f Dockerfile.api -t cyber-legends-api .
docker build -f Dockerfile.worker -t cyber-legends-worker .
docker compose -f docker-compose.production.yml up -d --build
```

Set production secrets and `DATABASE_URL` externally. Images contain no `.env` file
and run as a non-root user. Compose waits for PostgreSQL, runs `alembic upgrade head`
once, then starts API and worker. Verify `/ready`, worker heartbeat, and migrations.

## Rollout and Rollback

1. Back up PostgreSQL and record the current application/migration revision.
2. Build immutable API and worker tags from the same SHA.
3. Run migration drift and tests before rollout.
4. Deploy migration, API, then worker; watch readiness, dead letters, and outbox lag.
5. For application rollback, restore both images to the prior SHA. Run Alembic
   downgrade only after reviewing migration data-loss implications and taking a backup.

CI runs migrations, Ruff, format, Mypy, Bandit, PostgreSQL tests, coverage,
deterministic evaluation gates, dependency audit, both image builds, Trivy scans, and
SBOM generation. Run Locust separately with `locust -f tests/load/locustfile.py`.

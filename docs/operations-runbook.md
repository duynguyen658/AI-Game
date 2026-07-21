# Operations Runbook

## Routine Checks

1. Check `GET /live`, then `GET /ready`.
2. Inspect `GET /operations/summary` with a MANAGER/ADMIN token.
3. Inspect `/metrics` with `Authorization: Bearer $METRICS_TOKEN` for queue age,
   failures, and request latency. Never expose this token to end users.
4. Filter `GET /jobs` and `GET /alerts` before taking corrective action.

Every operator retry, cancel, or reconciliation call is bounded and authorized. Use
`POST /operations/jobs/reconcile`, `/outbox/reconcile`, `/memory/reconcile`, and
`/alerts/reconcile`; there is no generic command endpoint.

## Shutdown and Restart

Send SIGTERM and allow at least `JOB_LEASE_SECONDS` plus handler cleanup time. The
worker stops polling, finishes or loses its current lease, records STOPPED when
possible, and closes the engine. After restart, expired RUNNING jobs are reclaimed.
Outbox heartbeat failures invalidate the consumer result and roll back uncommitted
side effects; an expired event is reclaimed by fencing version.

## Retention and Dashboard

`AUDIT_RETENTION_DAYS` documents the retention target; destructive purge is not
automatic in v1. Export or archive audit data under an approved policy before manual
deletion. The backend has no frontend, so the M6 dashboard is deferred; use operator
APIs and Prometheus/Grafana integrations.

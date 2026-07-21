# M6 Production Architecture

## Request and Execution Path

```text
FastAPI -> application service -> PostgreSQL job/outbox -> worker
worker -> deterministic workflow -> bounded agents -> policy/actions -> PostgreSQL
```

The API enqueues long work and returns `202`. Workers lease with `FOR UPDATE SKIP
LOCKED`, commit the lease, and run handlers without holding queue locks. Heartbeats
renew a bounded lease. Completion is fenced by worker ID and lease expiry, so a stale
worker cannot finalize a reclaimed job.

Business transitions create outbox events before the same commit. Dispatch leases
events in short transactions, invokes idempotent consumers, then marks the event
processed. Failed events remain queryable and retry with bounded backoff.

## Operational Signals

- UUID correlation IDs flow through HTTP, jobs, and outbox events.
- Structured logs contain safe identifiers, status, duration, and stable error codes.
- Prometheus labels use bounded route/type/status values, never resource UUIDs.
- OpenTelemetry API spans are no-ops when no SDK/exporter is installed.
- `/live`, `/health`, and `/ready` separate process, summary, and dependency health.

The database is authoritative for jobs, attempts, worker heartbeats, outbox events,
alerts, evaluation runs/results, and all M3-M5 audit state. External publishing,
vector memory, autonomous supervision, and arbitrary network/shell/SQL tools remain
outside the architecture.

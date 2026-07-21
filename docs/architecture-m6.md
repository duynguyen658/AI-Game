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

Business transitions create outbox events before the same commit. Dispatch leases one
event per processing task with `lease_expires_at`, heartbeat, worker ownership, and a
monotonically increasing fencing version. The consumer transaction includes both its
idempotent side effect and the fenced `PROCESSED` update. Lease loss rolls that
transaction back; the stale owner neither marks failed nor retries a terminal write.
Failed events remain queryable and retry with bounded backoff.

Jobs retry only explicit transient classes. Unknown exceptions and permanent domain,
authorization, policy, validation, and state errors are non-retryable by default.

## Operational Signals

- UUID correlation IDs flow through HTTP, jobs, and outbox events.
- Structured logs contain safe identifiers, status, duration, and stable error codes.
- Prometheus labels use bounded route/type/status values, never resource UUIDs.
- `/metrics` requires a dedicated monitoring bearer token.
- Request middleware counts actual ASGI body chunks; `Content-Length` is only a fast
  pre-check.
- OpenTelemetry API spans are no-ops when no SDK/exporter is installed.
- `/live`, `/health`, and `/ready` separate process, summary, and dependency health.

The database is authoritative for jobs, attempts, worker heartbeats, outbox events,
alerts, evaluation runs/results, and all M3-M5 audit state. External publishing,
vector memory, autonomous supervision, and arbitrary network/shell/SQL tools remain
outside the architecture.

Evaluation-owned campaigns and workflows carry run/case ownership and are excluded
from campaign listings. `SYSTEM` mode executes the real workflow and Agentic runtime
with deterministic `MockLLMClient` scripts; `SNAPSHOT` only scores stored output.

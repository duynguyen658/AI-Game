# Job Recovery Runbook

## Stale Lease

1. Confirm the worker heartbeat is stale and the lease expired.
2. Call `POST /operations/jobs/reconcile?limit=100`.
3. Verify the attempt closed with `JOB_LEASE_EXPIRED`.
4. Verify the job is PENDING with a future `available_at`, or DEAD_LETTER at its
   attempt bound.

Completion is fenced by owner and lease expiry. Do not manually update lock columns.

## Failed and Dead-Letter Jobs

Retryable failures use persisted bounded exponential backoff. Non-retryable payload
or type failures move directly to DEAD_LETTER. An operator may call
`POST /jobs/{job_id}/retry` after correcting the condition; exhausted jobs receive one
explicit additional attempt. Cancel only at handler-safe checkpoints.

## Outbox Recovery

Call `POST /operations/outbox/reconcile`. A consumer failure remains FAILED with its
safe error and next availability. Exhausted events remain DEAD_LETTER and must not be
deleted to hide the incident. Verify consumer idempotency before manual replay.

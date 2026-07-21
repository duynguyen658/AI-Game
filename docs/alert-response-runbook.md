# Alert Response Runbook

Alerts are deterministic database records. Repeated conditions in the same hourly
bucket increment `occurrence_count`; acknowledgment does not resolve the condition.

1. Query `GET /alerts?status=OPEN` and inspect resource IDs and safe details.
2. Acknowledge ownership with `POST /alerts/{alert_id}/acknowledge`.
3. Correct the queue, action, memory, migration, PostgreSQL, or outbox condition.
4. Run `POST /operations/alerts/reconcile` when appropriate.
5. Resolve with `POST /alerts/{alert_id}/resolve` after verification.

For migration mismatch, stop API/worker rollout and run the migration gate. For
PostgreSQL outage, preserve application logs and restore database health before job
reconciliation. Never expose credentials or raw provider payloads in alert details.

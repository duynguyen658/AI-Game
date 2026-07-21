# Backend Contract Changes

## Baseline gaps

- There is no login, refresh, logout, or session endpoint.
- Applied task and media endpoints support create and detail, not collection reads.
- Provider comparisons support create and detail, not a collection read.
- Campaign decisions are write-only and workflows have no collection read.
- n8n APIs are signed inbound webhooks, not a status or delivery read model.

## M8 policy

The initial vertical slice uses existing contracts. A frontend BFF stores only a demo
identity in an HttpOnly cookie and injects development headers server-side. It is
disabled when demo auth is not explicitly enabled and is documented as non-production.

Collection screens never invent backend rows. Where a read contract is absent, they
show a precise empty/unsupported state or accept a known resource ID from a prior
creation. Any later backend additions will be limited to safe read models, pagination,
filters, sorting, display labels, timelines, or CORS and recorded here before use.

## Job status read model

M8 adds authenticated `GET /jobs/{job_id}/status` and points workflow enqueue
responses to it. The response excludes payload, idempotency key, worker identity,
lease metadata, trace ID, and attempts. Non-operator users can read only the
user-facing workflow, experiment, comparison, media, CSV, document, and storyboard
job types. Full job reads and all job mutations remain manager/admin only.

## Safe workflow timelines

The existing campaign and workflow timeline responses contain sanitized summaries,
status, timestamps, correlation IDs, and bounded metadata. M8 now permits any
authenticated actor to read those two timelines so task owners can follow progress.
Operations summary and every reconciliation command remain manager/admin only.

## Media content delivery

M8 adds authenticated `GET /media/assets/{asset_id}/content`. It resolves only the
opaque `media://` filename inside the configured storage root and returns the file
with its persisted MIME type. Invalid paths, traversal, absent files, and assets that
are not ready fail safely. The frontend never receives or constructs filesystem paths.

## Manager collection reads

M8 adds paginated `GET /prompt-templates/{template_id}/versions` for version history
and `GET /provider-comparisons` for the comparison workspace. Both return existing
safe Pydantic read schemas in deterministic newest-first order. Lifecycle commands,
winner selection, report metrics, and authorization remain unchanged.

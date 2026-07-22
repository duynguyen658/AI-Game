# Backend Contract Changes

## Baseline gaps closed in M8

- Production identity is handled by frontend OIDC routes and the existing FastAPI Bearer boundary; demo identity remains explicit and isolated.
- Applied tasks, data tasks, document tasks, media assets, storyboards, workflows, provider comparisons, and n8n deliveries now have bounded safe collection reads.
- Campaign/workflow/job/task/media reads are filtered by reusable resource-access policy.

## M8 policy

The BFF stores an encrypted HttpOnly session. In OIDC mode it forwards only the
server-side access token as Bearer authentication. In explicit demo mode it derives
development actor headers from the encrypted session, never browser headers.
Collection screens use backend-owned, paginated read models and do not compute or
invent domain state.

## Job status read model

M8 adds authenticated `GET /jobs/{job_id}/status` and points workflow enqueue
responses to it. The response excludes payload, idempotency key, worker identity,
lease metadata, and attempts. Resource-linked status and detail reads require access
to the referenced campaign, workflow, task, media asset, experiment, or comparison.
All job mutations remain manager/admin only and audited.

## Safe workflow timelines

The existing campaign and workflow timeline responses contain sanitized summaries,
status, timestamps, correlation IDs, and bounded metadata. M8 permits only actors
with campaign/workflow access to read them. Business users receive a reduced event
view without operator metadata or correlation details. Operations summary and every
reconciliation command remain manager/admin only.

## Media content delivery

M8 adds authenticated `GET /media/assets/{asset_id}/content`. It resolves only the
opaque `media://` filename inside the configured storage root and returns the file
with its persisted MIME type. Invalid paths, traversal, absent files, and assets that
are not ready fail safely. The frontend never receives or constructs filesystem paths.

## Product collection reads

M8 adds bounded, stable collection reads for applied tasks, CSV analysis, documents,
media assets, storyboards, workflows, prompt versions, provider comparisons, and n8n
deliveries. Normal users receive owner-filtered rows; elevated roles receive only the
broader scope defined by the access policy. Lifecycle commands, winner selection,
report metrics, and backend authorization remain authoritative.

# Media Workflow Guide

Image requests create a media audit row and typed job. Clients should send `X-Idempotency-Key`; retries by the same actor resolve to the original asset and job. The worker invokes Mock or the configured OpenAI adapter outside a database transaction, checks output presence, MIME signature, dimensions, provider flags, cost, and storage URI, then marks the asset `READY_FOR_REVIEW`.

A reviewer, manager, or admin must approve or reject the immutable result. Approval emits an outbox event but never publishes externally. Storyboards follow the same review boundary. Real video generation remains disabled and is not implemented as a publishing path.

Image and storyboard requests resolve managed prompts and persist template/version/hash plus model configuration. Every external provider call creates a numbered `STARTED` attempt before invocation, then finishes as `COMPLETED`, `FAILED`, or `CANCELLED` with duration, cost, provider job ID, and safe errors. Retries increment the attempt number. Generation emits `MEDIA_READY_FOR_REVIEW` once; review emits exactly one `MEDIA_APPROVED` or `MEDIA_REJECTED` event using an idempotency key.

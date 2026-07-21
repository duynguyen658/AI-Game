# n8n Integration Guide

Inbound calls require `X-N8N-Timestamp`, `X-N8N-Signature`, and `X-Idempotency-Key`. Compute the signature as lowercase HMAC-SHA256 over `timestamp + "." + raw_body` using `N8N_WEBHOOK_SECRET`. Stale signatures, changed bodies, replay with a new key, oversized bodies, and rate-limit violations are rejected safely.

Import the files under `automation/n8n`, configure credentials and environment variables, connect each error output, and only then activate workflows. Keep the signing secret in a credential-backed gateway or Code node. The backend does not accept arbitrary callback URLs or log secrets.

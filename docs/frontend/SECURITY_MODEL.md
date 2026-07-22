# M8 Security Model

## Trust boundaries

The browser is untrusted. Route guards improve navigation but grant no data access. The Next.js BFF authenticates its encrypted HttpOnly session, strips browser credentials and actor headers, then forwards either a server-held Bearer token in OIDC mode or server-created development headers in explicit demo mode. FastAPI validates the identity again and makes the final authorization decision.

## Resource policy

Campaigns have a persisted `created_by` owner. Workflows inherit campaign access. Applied tasks and media use their creator and campaign relation. Jobs resolve their workflow, task, media, experiment, or comparison payload before status/detail access. Marketing users receive only owned resources; reviewers receive reviewable resources; managers have broader business and operator access; admins and internal system execution have explicit overrides. UUID knowledge never grants access.

Business timelines omit tool calls, memory records, policy details, metadata, and correlation IDs for non-operator users. Operator mutations remain manager/admin restricted and audited. n8n inbound routes use timestamped HMAC and replay receipts; the delivery collection is operator-only and excludes signatures and raw request bodies.

## Session and upload controls

OIDC uses Authorization Code with PKCE, state, and nonce through `openid-client`. Production uses `OIDC_SESSION_STORAGE=postgres`: the `Secure`, `HttpOnly`, `SameSite=Lax` cookie contains only a 256-bit random ID, PostgreSQL stores only its hash, and access, refresh, and ID tokens are encrypted at rest with AES-256-GCM. Tokens are never placed in localStorage, returned by an API route, or logged.

The access token has its provider lifetime; the authenticated session has a separate fixed 10-hour maximum. Refresh begins 90 seconds before access expiry and remains possible after access expiry while the absolute session is valid. Rotation is persisted by refresh claim and version compare-and-swap. Invalid grants, malformed responses, unavailable providers, expired sessions, and revoked records clear local authentication and produce a stable 401 without forwarding a stale token. `AUTH_COOKIE_MAX_BYTES=3800` is enforced before every cookie is emitted; opaque production cookies remain far below it.

The BFF checks declared length and counts every streamed byte. JSON and multipart limits are separate, malformed or understated lengths cannot bypass the stream counter, cancellation propagates upstream, and complete request bodies are not allocated. Ingress, BFF, and backend limits must be configured as one documented policy.

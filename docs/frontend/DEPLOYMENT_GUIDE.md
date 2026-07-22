# Frontend Deployment Guide

The production image is multi-stage, uses Next standalone output, and runs as the unprivileged `nextjs` user. Build and start the full stack with:

```bash
docker compose -f docker-compose.production.yml up --build
```

Production uses `AUTH_MODE=oidc`, `DEMO_AUTH_ENABLED=false`, `OIDC_SESSION_STORAGE=postgres`, and the internal `BACKEND_API_URL=http://api:8000`. Required values include PostgreSQL/JWT secrets, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_JWKS_URL`, `SESSION_SECRET`, `OIDC_SESSION_ENCRYPTION_KEY`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, and `OIDC_POST_LOGOUT_REDIRECT_URI`. The provider must issue JWT access tokens whose subject, audience, issuer, signing key, and configured role claim are valid for FastAPI. Compose rejects missing values and does not publish the API port. All of these values are server-only and must never use a `NEXT_PUBLIC_*` prefix.

API and worker mount the same `media_production_data` volume at `/app/var/media`; the non-root image owns that path. Replace this volume with durable object storage in a later scoped deployment only after preserving the opaque media URI contract. `DEMO_PROVIDER_ALIASES` must remain false in production.

The OIDC client uses Authorization Code flow with PKCE, state, and nonce. Use `OIDC_SESSION_MAX_AGE_SECONDS=36000`, `OIDC_REFRESH_SKEW_SECONDS=90`, and `AUTH_COOKIE_MAX_BYTES=3800`; an optional `OIDC_SESSION_IDLE_TIMEOUT_SECONDS` is available only with PostgreSQL storage and must be bounded by the absolute lifetime. Access-token expiration does not end the authenticated session, and refresh remains possible while the absolute session is valid. The absolute expiry never slides on refresh. The opaque cookie contains no token; encrypted tokens are forwarded as Bearer only by the BFF. `OIDC_TEST_ISSUER_ENABLED` must remain false in production.

Logout revokes the PostgreSQL record before redirecting to the provider. Local revocation still succeeds when discovery or provider logout is unavailable. Run bounded expired-session cleanup through `deleteExpiredSessions`; revoked records are retained for 24 hours before cleanup to reject reuse during the audit window.

The demo stack is explicit:

```bash
docker compose -f docker-compose.demo.yml up -d --build
```

It sets `AUTH_MODE=demo`, enables development actor headers, uses mock providers, and must not be exposed as production. Body limits are layered: `BFF_MAX_BODY_BYTES` for ordinary bodies, `BFF_MAX_UPLOAD_BYTES` for multipart uploads, and backend `MAX_REQUEST_BODY_BYTES`/`MAX_UPLOAD_BYTES`. An ingress limit must be at least as strict as the intended public policy.

Rollback is image based. Database downgrade is not implied by a frontend rollback. Confirm OpenAPI compatibility, API readiness, worker freshness, queue depth, OIDC callback/logout, BFF-to-API connectivity, and the login/dashboard smoke before shifting traffic.

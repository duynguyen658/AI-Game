# Frontend Architecture

M8 is a Next.js App Router application in `frontend/`. Server components protect workspace routes and read an encrypted, expiring HttpOnly session. Client components own forms, TanStack Query caches, polling, tables, charts, and human decisions.

```text
Browser -> Next.js session/BFF routes -> FastAPI -> service/repository -> PostgreSQL
                                      -> PostgreSQL worker -> provider adapter
```

The browser calls only `/api/backend/*`. In OIDC mode, the BFF loads the server-side access token and sends `Authorization: Bearer`; in explicit demo mode it creates development actor headers from the encrypted session. Browser authorization, actor, cookie, forwarding, and provider-key headers are discarded. Request and response bodies stream, with header prechecks plus actual-byte limits.

Generated types in `frontend/generated/openapi.ts` come from the committed `openapi.m8.json`. Domain API modules translate route details into stable frontend calls. Async workflows retain backend job IDs and poll the safe status endpoint until a terminal state. Campaign timelines and review records remain backend authoritative.

Authentication is isolated behind `AuthAdapter`. `DemoAuthAdapter` is limited to the explicit demo deployment. `OidcAuthAdapter` performs discovery, Authorization Code flow, PKCE/state/nonce validation, server-side refresh, and provider logout without exposing tokens to client JavaScript. FastAPI remains the final authentication and resource-authorization boundary.

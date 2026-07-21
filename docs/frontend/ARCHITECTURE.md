# Frontend Architecture

M8 is a Next.js App Router application in `frontend/`. Server components protect workspace routes and read the signed HttpOnly demo session. Client components own forms, TanStack Query caches, polling, tables, charts, and human decisions.

```text
Browser -> Next.js session/BFF routes -> FastAPI -> service/repository -> PostgreSQL
                                      -> PostgreSQL worker -> provider adapter
```

The browser calls only `/api/backend/*`. The BFF validates the session, injects development actor headers server-side, strips unsafe headers, and normalizes backend-unavailable responses. Provider keys, webhook secrets, database credentials, and actor authorization headers never enter browser storage.

Generated types in `frontend/generated/openapi.ts` come from the committed `openapi.m8.json`. Domain API modules translate route details into stable frontend calls. Async workflows retain backend job IDs and poll the safe status endpoint until a terminal state. Campaign timelines and review records remain backend authoritative.

Authentication is deliberately isolated. The current demo adapter is suitable for local demonstrations. Production deployment must replace it with organizational SSO without changing the workspace or API modules.

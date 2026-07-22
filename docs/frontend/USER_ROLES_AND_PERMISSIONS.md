# User Roles and Permissions

The backend roles are `marketing`, `reviewer`, `manager`, `admin`, and `system`.
`system` is never offered as an interactive frontend identity.

| Capability | marketing | reviewer | manager | admin |
| --- | --- | --- | --- | --- |
| Create campaigns and applied tasks | Yes | Catalog dependent | Catalog dependent | Catalog dependent |
| View own task outputs | Yes | Yes | Yes | Yes |
| Decide campaign approval | No | Yes | Yes | Yes |
| View agent and controlled-action audits | No | Yes | Yes | Yes |
| Approve controlled actions | No | Role threshold | Role threshold | Yes |
| Manage prompts and experiments | No | Read/review | Yes | Yes |
| View business impact | Authenticated | Authenticated | Yes | Yes |
| Jobs, alerts, operations summary | No | No | Yes | Yes |

The frontend uses this matrix for navigation and affordances only. Every request is
still authorized by FastAPI. A hidden route or button is not treated as security.

Development supports a clearly labeled demo adapter using `x-actor-id` and
`x-actor-role`. Production expects backend-issued JWTs and a real identity provider;
the repository currently has no login or refresh endpoint.

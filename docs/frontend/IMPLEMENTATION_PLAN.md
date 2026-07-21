# Implementation Plan

1. Preserve the M7 baseline and generate OpenAPI types.
2. Build environment validation, session BFF, API client, Query provider, and errors.
3. Build the responsive application shell and role-aware navigation.
4. Complete campaign creation, asynchronous job polling, timeline, review, feedback,
   and impact as the first stable vertical slice.
5. Add task catalog, CSV, document, image, and storyboard workspaces.
6. Add prompt, experiment, provider, approval, and business-impact management.
7. Add jobs, alerts, health, and n8n operational surfaces.
8. Add tests, accessibility verification, Docker, CI, demo assets, and documentation.

Server resources live in TanStack Query. Forms use React Hook Form and Zod. Tables use
TanStack Table. No large global backend-resource store is introduced.

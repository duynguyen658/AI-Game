# Stable M8 API Contracts

M8 can build tables and detail pages from `GET /applied-workflows`, prompt/version endpoints, experiments, `/providers`, media assets, applied tasks, and `/jobs`. Filters and charts use analytics endpoints. Upload forms use multipart CSV/document tasks; approval dialogs use prompt activation and media review commands.

Stable identifiers are UUIDs except campaign IDs. Statuses are enums. Timestamps are timezone-aware ISO 8601 values. Money and rates are serialized decimals. Job-backed commands return HTTP 202 and a job or task link. Responses are Pydantic schemas rather than ORM payloads.

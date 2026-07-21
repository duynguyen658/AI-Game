# Backend API Map

Source of truth: generated `openapi.m8.json` from `app.main.app.openapi()` at M8 start.
The baseline contains 86 paths and 104 component schemas.

| Frontend area | Authoritative endpoints |
| --- | --- |
| Auth | Bearer JWT, or non-production `x-actor-id` and `x-actor-role` headers |
| Dashboard | `/operations/summary`, `/analytics/business-impact`, `/jobs`, `/alerts` |
| Campaigns | `/campaigns`, `/workflows/campaigns/{id}`, `/workflows/{id}/run`, `/approvals` |
| Timeline | `/operations/campaigns/{id}/timeline`, `/operations/workflows/{id}/timeline` |
| Tasks | `/applied-workflows` and workflow-specific task endpoints |
| CSV | `/data-analysis/tasks`, `/data-analysis/tasks/{id}/report` |
| Documents | `/document-processing/tasks`, `/document-processing/tasks/{id}/result` |
| Media | `/media/images`, `/media/assets/{id}`, review commands, storyboard endpoints |
| Prompts | `/prompt-templates`, `/prompt-versions/{id}`, lifecycle commands |
| Experiments | `/prompt-experiments` and run, cancel, result endpoints |
| Providers | `/providers`, `/provider-comparisons` and run, cancel, result endpoints |
| Impact | `/task-baselines`, `/task-runs/{id}/impact`, feedback, analytics endpoints |
| Actions | `/action-requests` and approval, rejection, execution endpoints |
| Operations | `/jobs`, `/alerts`, `/operations/summary`, `/live`, `/ready` |
| n8n | Signed write-only webhook endpoints plus repository workflow JSON files |

Lists use backend query parameters as generated. Statuses come only from OpenAPI enums.
The API returns safe domain exceptions and the operational middleware propagates
`X-Correlation-ID`. The frontend normalizes HTTP errors and displays that identifier.

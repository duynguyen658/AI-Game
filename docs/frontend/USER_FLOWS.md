# User Flows

## Campaign vertical slice

1. Choose a non-system demo role and establish an HttpOnly frontend session.
2. Load authorized navigation and dashboard data.
3. Create a campaign with the backend `CampaignCreate` contract.
4. Create a workflow, enqueue it, and poll the returned job.
5. Read campaign, workflow, agent summary, and backend timeline.
6. Approve, reject, or request revision when the workflow supports the action.
7. Submit feedback for eligible applied task runs and refresh impact analytics.

## Applied task

1. Select a workflow from `GET /applied-workflows`.
2. Use a purpose-specific form or validated file upload.
3. Receive a task or asset linked to an asynchronous job.
4. Poll only while the status is pending or running.
5. Read the authoritative report or result endpoint.
6. Review media or submit feedback where supported.

## Management and operations

Managers govern prompt lifecycle, experiments, provider comparisons, and metrics.
Operators inspect jobs, alerts, health, and reconciliation commands. Sensitive
mutations require a confirmation dialog and wait for server confirmation before the
UI changes state.

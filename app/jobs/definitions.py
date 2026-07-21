from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.core.constants import JobType, UserRole
from app.core.exceptions import JobPayloadError


class JobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkflowRunJobPayload(JobPayload):
    workflow_id: UUID


class ActionExecutionJobPayload(JobPayload):
    action_request_id: UUID
    expected_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: UserRole


class MemoryReconciliationJobPayload(JobPayload):
    limit: int = Field(default=100, ge=1, le=100)


class OutboxDispatchJobPayload(JobPayload):
    limit: int = Field(default=50, ge=1, le=100)


class EvaluationRunJobPayload(JobPayload):
    evaluation_run_id: UUID


class AlertReconciliationJobPayload(JobPayload):
    limit: int = Field(default=100, ge=1, le=500)


class LeasedJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    job_type: JobType
    payload: dict[str, object]
    attempt_count: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    correlation_id: str
    trace_id: str | None = None


TypedJobPayload = Annotated[
    WorkflowRunJobPayload
    | ActionExecutionJobPayload
    | MemoryReconciliationJobPayload
    | OutboxDispatchJobPayload
    | EvaluationRunJobPayload
    | AlertReconciliationJobPayload,
    Field(discriminator=None),
]

PAYLOAD_MODELS: dict[JobType, type[JobPayload]] = {
    JobType.WORKFLOW_RUN: WorkflowRunJobPayload,
    JobType.ACTION_EXECUTION: ActionExecutionJobPayload,
    JobType.MEMORY_RECONCILIATION: MemoryReconciliationJobPayload,
    JobType.OUTBOX_DISPATCH: OutboxDispatchJobPayload,
    JobType.EVALUATION_RUN: EvaluationRunJobPayload,
    JobType.ALERT_RECONCILIATION: AlertReconciliationJobPayload,
}


def validate_job_payload(job_type: JobType, payload: object) -> JobPayload:
    model = PAYLOAD_MODELS.get(job_type)
    if model is None:
        raise JobPayloadError("Unsupported job type")
    try:
        return TypeAdapter(model).validate_python(payload)
    except ValueError as exc:
        raise JobPayloadError("Job payload is invalid") from exc

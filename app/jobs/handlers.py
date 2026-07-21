from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.constants import ActionExecutionStatus, CampaignStatus, JobType
from app.core.exceptions import JobPayloadError
from app.evaluation.runner import EvaluationRunner
from app.jobs.definitions import (
    ActionExecutionJobPayload,
    AlertReconciliationJobPayload,
    EvaluationRunJobPayload,
    LeasedJob,
    MemoryReconciliationJobPayload,
    OutboxDispatchJobPayload,
    WorkflowRunJobPayload,
    validate_job_payload,
)
from app.jobs.worker import JobControl, JobHandler
from app.llm.factory import build_llm_client
from app.llm.base import LLMClient
from app.operations.alert_rules import AlertReconciler
from app.outbox.dispatcher import OutboxDispatcher
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.service.action_service import ActionService
from app.service.auth_service import AuthenticatedActor
from app.service.workflow_service import WorkflowService
from app.workflows.campaign_workflow import CampaignWorkflow


def build_job_handlers(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings | None = None,
    llm_client_factory: Callable[[], LLMClient] | None = None,
) -> Mapping[JobType, JobHandler]:
    config = settings or get_settings()
    client_factory = llm_client_factory or (lambda: build_llm_client(config))

    async def workflow_run(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, WorkflowRunJobPayload):
            raise JobPayloadError("Workflow job payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            workflow = await WorkflowService(session).get_workflow(payload.workflow_id)
            if workflow.status in {
                CampaignStatus.PENDING_APPROVAL,
                CampaignStatus.MANUAL_REVIEW_REQUIRED,
                CampaignStatus.APPROVED,
                CampaignStatus.REJECTED,
                CampaignStatus.FAILED,
            }:
                return
            await CampaignWorkflow(session, client_factory()).run_to_pending_approval(
                payload.workflow_id
            )

    async def action_execution(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, ActionExecutionJobPayload):
            raise JobPayloadError("Action job payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            executions = await ActionExecutionRepository(session).list_by_request(
                payload.action_request_id
            )
            if any(
                execution.status
                in {
                    ActionExecutionStatus.COMPLETED.value,
                    ActionExecutionStatus.FAILED.value,
                    ActionExecutionStatus.CANCELLED.value,
                }
                for execution in executions
            ):
                await session.commit()
                return
            await ActionService(session, settings=config).execute(
                payload.action_request_id,
                actor=AuthenticatedActor(
                    actor_id=payload.actor_id, role=payload.actor_role
                ),
                expected_version=payload.expected_version,
            )

    async def memory_reconciliation(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, MemoryReconciliationJobPayload):
            raise JobPayloadError("Memory job payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            await ActionService(
                session, settings=config
            ).reconcile_pending_action_memories(limit=payload.limit)

    async def outbox_dispatch(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, OutboxDispatchJobPayload):
            raise JobPayloadError("Outbox job payload does not match its type")
        await control.checkpoint()
        await OutboxDispatcher(
            f"{control.worker_id}:outbox",
            session_factory=session_factory,
            settings=config,
        ).dispatch_once(limit=payload.limit)

    async def evaluation_run(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, EvaluationRunJobPayload):
            raise JobPayloadError("Evaluation job payload does not match its type")
        await EvaluationRunner(session_factory=session_factory).run(
            payload.evaluation_run_id, checkpoint=control.checkpoint
        )

    async def alert_reconciliation(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, AlertReconciliationJobPayload):
            raise JobPayloadError("Alert job payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            await AlertReconciler(session, settings=config).reconcile(
                limit=payload.limit
            )

    return {
        JobType.WORKFLOW_RUN: workflow_run,
        JobType.ACTION_EXECUTION: action_execution,
        JobType.MEMORY_RECONCILIATION: memory_reconciliation,
        JobType.OUTBOX_DISPATCH: outbox_dispatch,
        JobType.EVALUATION_RUN: evaluation_run,
        JobType.ALERT_RECONCILIATION: alert_reconciliation,
    }

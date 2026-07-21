from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.constants import (
    ActionExecutionStatus,
    AppliedTaskStatus,
    CampaignStatus,
    JobType,
    OutboxEventType,
    ProviderName,
)
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
    DataAnalysisJobPayload,
    DocumentProcessingJobPayload,
    ImageGenerationJobPayload,
    VideoStoryboardJobPayload,
    PromptExperimentRunJobPayload,
    ProviderComparisonRunJobPayload,
    validate_job_payload,
)
from app.jobs.worker import JobControl, JobHandler
from app.llm.factory import build_llm_client
from app.llm.base import LLMClient
from app.llm.registry import build_provider_registry
from app.operations.alert_rules import AlertReconciler
from app.outbox.dispatcher import OutboxDispatcher
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.repositories.prompt_repository import PromptRepository
from app.service.action_service import ActionService
from app.service.auth_service import AuthenticatedActor
from app.service.workflow_service import WorkflowService
from app.workflows.campaign_workflow import CampaignWorkflow
from app.applied_workflows.data_analysis.processor import analyze_csv
from app.applied_workflows.document_processing.processor import process_document
from app.media.service import MediaProcessor
from app.outbox.service import OutboxService
from app.service.applied_workflow_service import AppliedWorkflowService
from app.prompt_management.runners import (
    PromptExperimentRunner,
    ProviderComparisonRunner,
)


def build_job_handlers(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings | None = None,
    llm_client_factory: Callable[[], LLMClient] | None = None,
    provider_client_factory: Callable[[ProviderName], LLMClient] | None = None,
) -> Mapping[JobType, JobHandler]:
    config = settings or get_settings()
    client_factory = llm_client_factory or (lambda: build_llm_client(config))
    provider_registry = build_provider_registry(config)
    comparison_client_factory = provider_client_factory or (
        lambda provider: cast(LLMClient, provider_registry.get(provider))
    )

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

    async def data_analysis(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, DataAnalysisJobPayload):
            raise JobPayloadError("Data analysis payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            task = await AppliedWorkflowService(session).required(payload.task_run_id)
            if task.status == AppliedTaskStatus.COMPLETED.value:
                return
            task = await AppliedWorkflowService(session).mark_processing(
                payload.task_run_id, commit=False
            )
            content = bytes(task.input_content or b"")
            filename = str(task.input_metadata.get("filename", "upload.csv"))
            prompt_version = (
                await PromptRepository(session).get_version(task.prompt_version_id)
                if task.prompt_version_id
                else None
            )
            if prompt_version is None:
                raise JobPayloadError("Managed data-analysis prompt is unavailable")
            await session.commit()
        report = await analyze_csv(
            content,
            filename=filename,
            settings=config,
            llm_client=client_factory(),
            prompt_version=prompt_version,
        )
        await control.checkpoint()
        async with session_factory() as session:
            await AppliedWorkflowService(session).complete(
                payload.task_run_id, report.model_dump(mode="json"), commit=False
            )
            await OutboxService(session).add_event(
                event_type=OutboxEventType.DATA_ANALYSIS_COMPLETED,
                aggregate_type="applied_task",
                aggregate_id=str(payload.task_run_id),
                payload={"task_run_id": str(payload.task_run_id)},
            )
            await session.commit()

    async def document_processing(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, DocumentProcessingJobPayload):
            raise JobPayloadError("Document processing payload does not match its type")
        await control.checkpoint()
        async with session_factory() as session:
            task = await AppliedWorkflowService(session).required(payload.task_run_id)
            if task.status == AppliedTaskStatus.COMPLETED.value:
                return
            task = await AppliedWorkflowService(session).mark_processing(
                payload.task_run_id, commit=False
            )
            content = bytes(task.input_content or b"")
            filename = str(task.input_metadata.get("filename", "upload.txt"))
            content_type = str(
                task.input_metadata.get("content_type", "application/octet-stream")
            )
            prompt_version = (
                await PromptRepository(session).get_version(task.prompt_version_id)
                if task.prompt_version_id
                else None
            )
            if prompt_version is None:
                raise JobPayloadError("Managed document prompt is unavailable")
            await session.commit()
        result = await process_document(
            content,
            filename=filename,
            content_type=content_type,
            settings=config,
            llm_client=client_factory(),
            prompt_version=prompt_version,
        )
        await control.checkpoint()
        async with session_factory() as session:
            await AppliedWorkflowService(session).complete(
                payload.task_run_id, result.model_dump(mode="json"), commit=False
            )
            await OutboxService(session).add_event(
                event_type=OutboxEventType.DOCUMENT_PROCESSING_COMPLETED,
                aggregate_type="applied_task",
                aggregate_id=str(payload.task_run_id),
                payload={"task_run_id": str(payload.task_run_id)},
            )
            await session.commit()

    async def image_generation(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, ImageGenerationJobPayload):
            raise JobPayloadError("Image generation payload does not match its type")
        await control.checkpoint()
        await MediaProcessor(
            session_factory, settings=config, llm_client=client_factory()
        ).generate_image(payload.media_asset_id)

    async def video_storyboard(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, VideoStoryboardJobPayload):
            raise JobPayloadError("Storyboard payload does not match its type")
        await control.checkpoint()
        await MediaProcessor(
            session_factory, settings=config, llm_client=client_factory()
        ).generate_storyboard(payload.media_asset_id)

    async def prompt_experiment_run(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, PromptExperimentRunJobPayload):
            raise JobPayloadError("Prompt experiment payload does not match its type")
        await PromptExperimentRunner(session_factory, comparison_client_factory).run(
            payload.experiment_id, checkpoint=control.checkpoint
        )

    async def provider_comparison_run(job: LeasedJob, control: JobControl) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if not isinstance(payload, ProviderComparisonRunJobPayload):
            raise JobPayloadError("Provider comparison payload does not match its type")
        await ProviderComparisonRunner(session_factory, comparison_client_factory).run(
            payload.comparison_id, checkpoint=control.checkpoint
        )

    return {
        JobType.WORKFLOW_RUN: workflow_run,
        JobType.ACTION_EXECUTION: action_execution,
        JobType.MEMORY_RECONCILIATION: memory_reconciliation,
        JobType.OUTBOX_DISPATCH: outbox_dispatch,
        JobType.EVALUATION_RUN: evaluation_run,
        JobType.ALERT_RECONCILIATION: alert_reconciliation,
        JobType.DATA_ANALYSIS: data_analysis,
        JobType.DOCUMENT_PROCESSING: document_processing,
        JobType.IMAGE_GENERATION: image_generation,
        JobType.VIDEO_STORYBOARD: video_storyboard,
        JobType.PROMPT_EXPERIMENT_RUN: prompt_experiment_run,
        JobType.PROVIDER_COMPARISON_RUN: provider_comparison_run,
    }

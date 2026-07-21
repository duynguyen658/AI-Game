from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AppliedTaskStatus,
    MediaAssetStatus,
    PromptExperimentStatus,
    ProviderComparisonStatus,
)
from app.core.sanitization import sanitize_text
from app.database.models import AppliedWorkflowTaskModel
from app.jobs.definitions import (
    DataAnalysisJobPayload,
    DocumentProcessingJobPayload,
    ImageGenerationJobPayload,
    LeasedJob,
    PromptExperimentRunJobPayload,
    ProviderComparisonRunJobPayload,
    VideoStoryboardJobPayload,
    validate_job_payload,
)
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.repositories.media_repository import MediaRepository
from app.repositories.prompt_experiment_repository import PromptExperimentRepository
from app.repositories.provider_comparison_repository import (
    ProviderComparisonRepository,
)


class JobTerminalReconciler:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reconcile(
        self,
        job: LeasedJob,
        *,
        cancelled: bool,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        task_status = (
            AppliedTaskStatus.CANCELLED.value
            if cancelled
            else AppliedTaskStatus.FAILED.value
        )
        media_status = (
            MediaAssetStatus.CANCELLED.value
            if cancelled
            else MediaAssetStatus.FAILED.value
        )
        experiment_status = (
            PromptExperimentStatus.CANCELLED.value
            if cancelled
            else PromptExperimentStatus.FAILED.value
        )
        comparison_status = (
            ProviderComparisonStatus.CANCELLED.value
            if cancelled
            else ProviderComparisonStatus.FAILED.value
        )
        now = datetime.now(UTC)
        safe_message = (
            sanitize_text(error_message, max_characters=2000) if error_message else None
        )

        if isinstance(payload, (DataAnalysisJobPayload, DocumentProcessingJobPayload)):
            task = await AppliedWorkflowRepository(self.session).get(
                payload.task_run_id
            )
            if task is not None and task.status not in {
                AppliedTaskStatus.COMPLETED.value,
                AppliedTaskStatus.CANCELLED.value,
            }:
                task.status = task_status
                task.error_code = error_code
                task.error_message = safe_message
                task.completed_at = now
                task.duration_ms = _duration_ms(task.started_at, now)
        elif isinstance(
            payload, (ImageGenerationJobPayload, VideoStoryboardJobPayload)
        ):
            asset = await MediaRepository(self.session).get_asset(
                payload.media_asset_id
            )
            if asset is not None and asset.status not in {
                MediaAssetStatus.APPROVED.value,
                MediaAssetStatus.REJECTED.value,
                MediaAssetStatus.READY_FOR_REVIEW.value,
            }:
                asset.status = media_status
                asset.error_code = error_code
                asset.error_message = safe_message
                asset.completed_at = now
                if asset.task_run_id is not None:
                    task = await AppliedWorkflowRepository(self.session).get(
                        asset.task_run_id
                    )
                    if task is not None:
                        task.status = task_status
                        task.error_code = error_code
                        task.error_message = safe_message
                        task.completed_at = now
                        task.duration_ms = _duration_ms(task.started_at, now)
        elif isinstance(payload, PromptExperimentRunJobPayload):
            experiment = await PromptExperimentRepository(self.session).get(
                payload.experiment_id
            )
            if experiment is not None:
                experiment.status = experiment_status
                experiment.error_code = error_code
                experiment.error_message = safe_message
                experiment.completed_at = now
        elif isinstance(payload, ProviderComparisonRunJobPayload):
            comparison = await ProviderComparisonRepository(self.session).get(
                payload.comparison_id
            )
            if comparison is not None:
                comparison.status = comparison_status
                comparison.error_code = error_code
                comparison.error_message = safe_message
                comparison.completed_at = now
        await self.session.commit()

    async def prepare_retry(self, job: LeasedJob) -> None:
        payload = validate_job_payload(job.job_type, job.payload)
        if isinstance(payload, (DataAnalysisJobPayload, DocumentProcessingJobPayload)):
            task = await AppliedWorkflowRepository(self.session).get(
                payload.task_run_id
            )
            if task is not None:
                _reset_task(task)
        elif isinstance(
            payload, (ImageGenerationJobPayload, VideoStoryboardJobPayload)
        ):
            asset = await MediaRepository(self.session).get_asset(
                payload.media_asset_id
            )
            if asset is not None:
                asset.status = MediaAssetStatus.REQUESTED.value
                asset.error_code = None
                asset.error_message = None
                asset.completed_at = None
                if asset.task_run_id is not None:
                    task = await AppliedWorkflowRepository(self.session).get(
                        asset.task_run_id
                    )
                    if task is not None:
                        _reset_task(task)
        elif isinstance(payload, PromptExperimentRunJobPayload):
            experiment = await PromptExperimentRepository(self.session).get(
                payload.experiment_id
            )
            if experiment is not None:
                experiment.status = PromptExperimentStatus.RUNNING.value
                experiment.error_code = None
                experiment.error_message = None
                experiment.completed_at = None
        elif isinstance(payload, ProviderComparisonRunJobPayload):
            comparison = await ProviderComparisonRepository(self.session).get(
                payload.comparison_id
            )
            if comparison is not None:
                comparison.status = ProviderComparisonStatus.RUNNING.value
                comparison.error_code = None
                comparison.error_message = None
                comparison.completed_at = None
        await self.session.commit()


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int:
    if started_at is None:
        return 0
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)


def _reset_task(task: AppliedWorkflowTaskModel) -> None:
    task.status = AppliedTaskStatus.PENDING.value
    task.error_code = None
    task.error_message = None
    task.completed_at = None

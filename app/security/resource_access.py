from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CampaignStatus, JobType, MediaAssetStatus, UserRole
from app.core.exceptions import (
    AuthorizationError,
    CampaignNotFoundError,
    JobNotFoundError,
    M7ResourceNotFoundError,
    WorkflowNotFoundError,
)
from app.database.models import (
    AppliedWorkflowTaskModel,
    BackgroundJobModel,
    CampaignModel,
    MediaAssetModel,
    PromptExperimentModel,
    ProviderComparisonModel,
    WorkflowRunModel,
)
from app.service.auth_service import AuthenticatedActor

ELEVATED_BUSINESS_ROLES = {UserRole.MANAGER, UserRole.ADMIN, UserRole.SYSTEM}
REVIEWABLE_CAMPAIGN_STATUSES = {
    CampaignStatus.REVIEWING.value,
    CampaignStatus.MANUAL_REVIEW_REQUIRED.value,
    CampaignStatus.PENDING_APPROVAL.value,
}


class ResourceAccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def has_business_override(actor: AuthenticatedActor) -> bool:
        return actor.role in ELEVATED_BUSINESS_ROLES

    async def require_campaign_access(
        self, actor: AuthenticatedActor, campaign_id: str, *, write: bool = False
    ) -> CampaignModel:
        campaign = await self.session.get(CampaignModel, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")
        allowed = (
            self.has_business_override(actor) or campaign.created_by == actor.actor_id
        )
        if not write and actor.role == UserRole.REVIEWER:
            allowed = campaign.status in REVIEWABLE_CAMPAIGN_STATUSES
        if not allowed:
            raise AuthorizationError("Actor cannot access this campaign")
        return campaign

    async def require_workflow_access(
        self, actor: AuthenticatedActor, workflow_id: UUID, *, write: bool = False
    ) -> WorkflowRunModel:
        workflow = await self.session.get(WorkflowRunModel, workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        await self.require_campaign_access(actor, workflow.campaign_id, write=write)
        return workflow

    async def require_task_access(
        self, actor: AuthenticatedActor, task_run_id: UUID
    ) -> AppliedWorkflowTaskModel:
        task = await self.session.get(AppliedWorkflowTaskModel, task_run_id)
        if task is None:
            raise M7ResourceNotFoundError("Applied workflow task not found")
        if not self.has_business_override(actor) and task.created_by != actor.actor_id:
            raise AuthorizationError("Actor cannot access this applied workflow task")
        return task

    async def require_media_access(
        self,
        actor: AuthenticatedActor,
        media_asset_id: UUID,
        *,
        review: bool = False,
    ) -> MediaAssetModel:
        asset = await self.session.get(MediaAssetModel, media_asset_id)
        if asset is None:
            raise M7ResourceNotFoundError("Media asset not found")
        if review:
            if actor.role not in {UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN}:
                raise AuthorizationError("Reviewer role is required")
            if (
                actor.role == UserRole.REVIEWER
                and asset.status != MediaAssetStatus.READY_FOR_REVIEW.value
            ):
                raise AuthorizationError("Media asset is not available for review")
            return asset
        if self.has_business_override(actor) or asset.created_by == actor.actor_id:
            return asset
        if (
            actor.role == UserRole.REVIEWER
            and asset.status == MediaAssetStatus.READY_FOR_REVIEW.value
        ):
            return asset
        if asset.campaign_id is not None:
            await self.require_campaign_access(actor, asset.campaign_id)
            return asset
        raise AuthorizationError("Actor cannot access this media asset")

    async def require_job_access(
        self, actor: AuthenticatedActor, job_id: UUID
    ) -> BackgroundJobModel:
        job = await self.session.get(BackgroundJobModel, job_id)
        if job is None:
            raise JobNotFoundError("Background job not found")
        if self.has_business_override(actor) or job.created_by == actor.actor_id:
            return job
        payload: dict[str, Any] = job.payload
        job_type = JobType(job.job_type)
        if job_type == JobType.WORKFLOW_RUN and payload.get("workflow_id"):
            await self.require_workflow_access(actor, UUID(str(payload["workflow_id"])))
            return job
        if job_type in {
            JobType.DATA_ANALYSIS,
            JobType.DOCUMENT_PROCESSING,
        } and payload.get("task_run_id"):
            await self.require_task_access(actor, UUID(str(payload["task_run_id"])))
            return job
        if job_type in {
            JobType.IMAGE_GENERATION,
            JobType.VIDEO_STORYBOARD,
        } and payload.get("media_asset_id"):
            await self.require_media_access(actor, UUID(str(payload["media_asset_id"])))
            return job
        if job_type == JobType.PROMPT_EXPERIMENT_RUN and payload.get("experiment_id"):
            experiment = await self.session.get(
                PromptExperimentModel, UUID(str(payload["experiment_id"]))
            )
            if experiment is not None and experiment.created_by == actor.actor_id:
                return job
        if job_type == JobType.PROVIDER_COMPARISON_RUN and payload.get("comparison_id"):
            comparison = await self.session.get(
                ProviderComparisonModel, UUID(str(payload["comparison_id"]))
            )
            if comparison is not None and comparison.created_by == actor.actor_id:
                return job
        raise AuthorizationError("Actor cannot access this background job")

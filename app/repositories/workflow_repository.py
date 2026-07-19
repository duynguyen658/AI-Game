from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CampaignStatus, WorkflowStep
from app.database.models import WorkflowRunModel

ACTIVE_WORKFLOW_STATUSES = {
    CampaignStatus.RECEIVED.value,
    CampaignStatus.VALIDATING.value,
    CampaignStatus.ANALYZING.value,
    CampaignStatus.GENERATING.value,
    CampaignStatus.REVIEWING.value,
    CampaignStatus.MANUAL_REVIEW_REQUIRED.value,
    CampaignStatus.PENDING_APPROVAL.value,
    CampaignStatus.REVISION_REQUIRED.value,
    CampaignStatus.NEEDS_CLARIFICATION.value,
}


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, campaign_id: str) -> WorkflowRunModel:
        model = WorkflowRunModel(campaign_id=campaign_id)
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(self, workflow_id: UUID) -> WorkflowRunModel | None:
        return await self.session.get(WorkflowRunModel, workflow_id)

    async def get_by_id_for_update(self, workflow_id: UUID) -> WorkflowRunModel | None:
        result = await self.session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.workflow_id == workflow_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_active_for_campaign(
        self,
        campaign_id: str,
    ) -> WorkflowRunModel | None:
        result = await self.session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.campaign_id == campaign_id)
            .where(WorkflowRunModel.status.in_(ACTIVE_WORKFLOW_STATUSES))
            .order_by(WorkflowRunModel.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_campaign(self, campaign_id: str) -> Sequence[WorkflowRunModel]:
        result = await self.session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.campaign_id == campaign_id)
            .order_by(WorkflowRunModel.started_at.desc())
        )
        return result.scalars().all()

    async def update_status(
        self,
        workflow: WorkflowRunModel,
        status: CampaignStatus,
    ) -> WorkflowRunModel:
        workflow.status = status.value
        await self.session.flush()
        return workflow

    async def update_current_step(
        self,
        workflow: WorkflowRunModel,
        step: WorkflowStep,
    ) -> WorkflowRunModel:
        workflow.current_step = step.value
        await self.session.flush()
        return workflow

    async def increment_llm_call_count(
        self,
        workflow: WorkflowRunModel,
    ) -> WorkflowRunModel:
        workflow.llm_call_count += 1
        await self.session.flush()
        return workflow

    async def increment_retry_count(
        self,
        workflow: WorkflowRunModel,
    ) -> WorkflowRunModel:
        workflow.retry_count += 1
        await self.session.flush()
        return workflow

    async def save_quality_score(
        self,
        workflow: WorkflowRunModel,
        score: int,
    ) -> WorkflowRunModel:
        workflow.quality_score = score
        await self.session.flush()
        return workflow

    async def mark_completed(self, workflow: WorkflowRunModel) -> WorkflowRunModel:
        workflow.current_step = WorkflowStep.COMPLETE.value
        workflow.completed_at = datetime.now(UTC)
        await self.session.flush()
        return workflow

    async def mark_failed(
        self,
        workflow: WorkflowRunModel,
        *,
        error_code: str,
        error_message: str,
    ) -> WorkflowRunModel:
        workflow.status = CampaignStatus.FAILED.value
        workflow.error_code = error_code
        workflow.error_message = error_message
        workflow.completed_at = datetime.now(UTC)
        await self.session.flush()
        return workflow

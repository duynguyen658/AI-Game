from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    ACTIVE_WORKFLOW_STATUSES,
    CampaignStatus,
    WorkflowStep,
)
from app.database.models import CampaignModel, WorkflowRunModel


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        campaign_id: str,
        *,
        status: CampaignStatus = CampaignStatus.RECEIVED,
        current_step: WorkflowStep = WorkflowStep.RECEIVE_CAMPAIGN,
        parent_workflow_id: UUID | None = None,
        revision_number: int = 0,
        evaluation_run_id: UUID | None = None,
        evaluation_case_id: UUID | None = None,
    ) -> WorkflowRunModel:
        if revision_number < 0:
            raise ValueError("revision_number must be non-negative")
        model = WorkflowRunModel(
            campaign_id=campaign_id,
            parent_workflow_id=parent_workflow_id,
            revision_number=revision_number,
            status=status.value,
            current_step=current_step.value,
            is_evaluation=evaluation_run_id is not None,
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
        )
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

    async def latest_revision_parent_for_campaign(
        self,
        campaign_id: str,
    ) -> WorkflowRunModel | None:
        result = await self.session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.campaign_id == campaign_id)
            .where(WorkflowRunModel.status == CampaignStatus.REVISION_REQUIRED.value)
            .where(WorkflowRunModel.completed_at.is_not(None))
            .order_by(
                WorkflowRunModel.revision_number.desc(),
                WorkflowRunModel.completed_at.desc(),
            )
            .limit(1)
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
            .where(WorkflowRunModel.completed_at.is_(None))
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

    async def list_accessible(
        self,
        *,
        limit: int,
        offset: int,
        campaign_id: str | None = None,
        owner_id: str | None = None,
        reviewable_only: bool = False,
    ) -> Sequence[WorkflowRunModel]:
        statement: Select[tuple[WorkflowRunModel]] = select(WorkflowRunModel).join(
            CampaignModel, CampaignModel.campaign_id == WorkflowRunModel.campaign_id
        )
        statement = statement.where(WorkflowRunModel.is_evaluation.is_(False))
        if campaign_id is not None:
            statement = statement.where(WorkflowRunModel.campaign_id == campaign_id)
        if owner_id is not None:
            statement = statement.where(CampaignModel.created_by == owner_id)
        if reviewable_only:
            statement = statement.where(
                CampaignModel.status.in_(
                    [
                        CampaignStatus.REVIEWING.value,
                        CampaignStatus.MANUAL_REVIEW_REQUIRED.value,
                        CampaignStatus.PENDING_APPROVAL.value,
                    ]
                )
            )
        result = await self.session.execute(
            statement.order_by(
                WorkflowRunModel.started_at.desc(), WorkflowRunModel.workflow_id
            )
            .offset(offset)
            .limit(limit)
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
        workflow.current_step = WorkflowStep.COMPLETE.value
        workflow.error_code = error_code
        workflow.error_message = error_message
        workflow.completed_at = datetime.now(UTC)
        await self.session.flush()
        return workflow

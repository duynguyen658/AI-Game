from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CampaignStatus, WorkflowStep
from app.core.exceptions import (
    CampaignNotFoundError,
    WorkflowAlreadyActiveError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow_run import WorkflowRun
from app.service.mappers import workflow_to_schema
from app.workflows.workflow_state import ensure_valid_transition


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repository = CampaignRepository(session)
        self.workflow_repository = WorkflowRepository(session)
        self.settings = get_settings()

    async def create_workflow(self, campaign_id: str) -> WorkflowRun:
        campaign = await self.campaign_repository.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")
        active = await self.workflow_repository.get_active_for_campaign(campaign_id)
        if active is not None:
            raise WorkflowAlreadyActiveError("Campaign already has an active workflow")
        workflow = await self.workflow_repository.create(campaign_id)
        await self.session.commit()
        return workflow_to_schema(workflow)

    async def get_workflow(self, workflow_id: UUID) -> WorkflowRun:
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        return workflow_to_schema(workflow)

    async def transition(
        self,
        workflow_id: UUID,
        next_status: CampaignStatus,
        *,
        step: WorkflowStep | None = None,
    ) -> WorkflowRun:
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        ensure_valid_transition(CampaignStatus(workflow.status), next_status)
        await self.workflow_repository.update_status(workflow, next_status)
        if step is not None:
            await self.workflow_repository.update_current_step(workflow, step)
        await self.session.commit()
        return workflow_to_schema(workflow)

    async def record_llm_call(self, workflow_id: UUID) -> None:
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        if workflow.llm_call_count >= self.settings.max_llm_calls_per_workflow:
            raise WorkflowLimitError("LLM call budget exhausted")
        await self.workflow_repository.increment_llm_call_count(workflow)
        await self.session.flush()

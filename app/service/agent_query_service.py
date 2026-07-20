from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AgentContextError,
    CampaignNotFoundError,
    WorkflowNotFoundError,
)
from app.core.sanitization import sanitize_json
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository


class AgentReadQueryService:
    """Fresh, lock-free reads exposed to the bounded M4 tool layer."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)

    async def get_previous_quality_review(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> object:
        campaign, _ = await self._load_pair(campaign_id, workflow_id)
        result = sanitize_json(campaign.quality_review or {"available": False})
        await self.session.commit()
        return result

    async def get_previous_revision(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> object:
        campaign, workflow = await self._load_pair(campaign_id, workflow_id)
        parent = (
            await self.workflows.get_by_id(workflow.parent_workflow_id)
            if workflow.parent_workflow_id
            else None
        )
        result = sanitize_json(
            {
                "available": parent is not None,
                "parent_workflow_id": str(parent.workflow_id) if parent else None,
                "revision_number": parent.revision_number if parent else None,
                "generated_content": campaign.generated_content if parent else None,
                "quality_review": campaign.quality_review if parent else None,
            }
        )
        await self.session.commit()
        return result

    async def get_previous_workflow_summary(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> object:
        _, workflow = await self._load_pair(campaign_id, workflow_id)
        parent = (
            await self.workflows.get_by_id(workflow.parent_workflow_id)
            if workflow.parent_workflow_id
            else None
        )
        result = sanitize_json(
            {
                "available": parent is not None,
                "workflow_id": str(parent.workflow_id) if parent else None,
                "status": parent.status if parent else None,
                "revision_number": parent.revision_number if parent else None,
                "quality_score": parent.quality_score if parent else None,
                "completed_at": parent.completed_at.isoformat()
                if parent and parent.completed_at
                else None,
            }
        )
        await self.session.commit()
        return result

    async def _load_pair(self, campaign_id: str, workflow_id: UUID):
        workflow = await self.workflows.get_by_id(workflow_id)
        if workflow is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaigns.get_by_id(campaign_id)
        if campaign is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        if workflow.campaign_id != campaign_id:
            await self.session.rollback()
            raise AgentContextError("Workflow does not belong to campaign")
        return campaign, workflow

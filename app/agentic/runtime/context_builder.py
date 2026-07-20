from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.state.campaign_context import CampaignContext
from app.core.exceptions import AgentContextError
from app.core.sanitization import sanitize_json, sanitize_text
from app.service.campaign_service import CampaignService
from app.service.workflow_service import WorkflowService


class AgentContextBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaigns = CampaignService(session)
        self.workflows = WorkflowService(session)

    async def build(self, *, campaign_id: str, workflow_id: UUID) -> CampaignContext:
        campaign = await self.campaigns.get_campaign(campaign_id)
        workflow = await self.workflows.get_workflow(workflow_id)
        if workflow.campaign_id != campaign_id:
            await self.session.rollback()
            raise AgentContextError("Workflow does not belong to campaign")
        context = CampaignContext(
            campaign_id=campaign_id,
            workflow_id=workflow_id,
            revision_number=workflow.revision_number,
            game_name=sanitize_text(campaign.campaign.game_name, max_characters=200),
            genre=sanitize_text(campaign.campaign.genre, max_characters=100),
            target_audience=sanitize_text(
                campaign.campaign.target_audience, max_characters=300
            ),
            market=sanitize_text(campaign.campaign.market, max_characters=100),
            platforms=tuple(campaign.campaign.platforms),
            campaign_objective=sanitize_text(
                campaign.campaign.campaign_objective, max_characters=1000
            ),
            tone=sanitize_text(campaign.campaign.tone, max_characters=500),
            launch_date=campaign.campaign.launch_date,
            promotion=sanitize_text(campaign.campaign.promotion, max_characters=1000),
            raw_brief=(
                sanitize_text(campaign.campaign.raw_brief, max_characters=20_000)
                if campaign.campaign.raw_brief
                else None
            ),
            current_workflow_status=workflow.status,
            retry_count=workflow.retry_count,
            brief_analysis=(
                sanitize_json(campaign.analysis.model_dump(mode="json"))
                if campaign.analysis
                else None
            ),
            generated_content=(
                sanitize_json(campaign.generated_content.model_dump(mode="json"))
                if campaign.generated_content
                else None
            ),
            quality_review=(
                sanitize_json(campaign.quality_review.model_dump(mode="json"))
                if campaign.quality_review
                else None
            ),
            parent_workflow_id=workflow.parent_workflow_id,
        )
        await self.session.commit()
        return context

    async def build_brief_analysis_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> CampaignContext:
        return await self.build(campaign_id=campaign_id, workflow_id=workflow_id)

    async def build_content_generation_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> CampaignContext:
        return await self.build(campaign_id=campaign_id, workflow_id=workflow_id)

    async def build_content_review_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> CampaignContext:
        return await self.build(campaign_id=campaign_id, workflow_id=workflow_id)

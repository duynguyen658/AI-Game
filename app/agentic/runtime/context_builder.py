from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.state.campaign_context import (
    BriefAnalysisContext,
    ContentGenerationContext,
    ContentReviewContext,
)
from app.core.exceptions import AgentContextError
from app.core.sanitization import sanitize_json, sanitize_text
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignRecord,
    GeneratedContent,
    QualityReview,
)
from app.schemas.workflow_run import WorkflowRun
from app.service.campaign_service import CampaignService
from app.service.workflow_service import WorkflowService

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AgentContextBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaigns = CampaignService(session)
        self.workflows = WorkflowService(session)

    async def build_brief_analysis_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> BriefAnalysisContext:
        campaign, workflow = await self._load_pair(campaign_id, workflow_id)
        context = BriefAnalysisContext.model_validate(
            {
                **self._workflow_fields(workflow),
                "game_name": sanitize_text(
                    campaign.campaign.game_name, max_characters=200
                ),
                "genre": sanitize_text(campaign.campaign.genre, max_characters=100),
                "target_audience": sanitize_text(
                    campaign.campaign.target_audience, max_characters=300
                ),
                "market": sanitize_text(campaign.campaign.market, max_characters=100),
                "platforms": tuple(campaign.campaign.platforms),
                "campaign_objective": sanitize_text(
                    campaign.campaign.campaign_objective, max_characters=1000
                ),
                "tone": sanitize_text(campaign.campaign.tone, max_characters=500),
                "launch_date": campaign.campaign.launch_date,
                "promotion": sanitize_text(
                    campaign.campaign.promotion, max_characters=1000
                ),
                "raw_brief": self._optional_text(campaign.campaign.raw_brief, 20_000),
            }
        )
        await self.session.commit()
        return context

    async def build_content_generation_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> ContentGenerationContext:
        campaign, workflow = await self._load_pair(campaign_id, workflow_id)
        if campaign.analysis is None:
            await self.session.rollback()
            raise AgentContextError("Content generation requires brief analysis")
        context = ContentGenerationContext.model_validate(
            {
                **self._workflow_fields(workflow),
                "game_name": sanitize_text(
                    campaign.campaign.game_name, max_characters=200
                ),
                "target_audience": sanitize_text(
                    campaign.campaign.target_audience, max_characters=300
                ),
                "market": sanitize_text(campaign.campaign.market, max_characters=100),
                "platforms": tuple(campaign.campaign.platforms),
                "campaign_objective": sanitize_text(
                    campaign.campaign.campaign_objective, max_characters=1000
                ),
                "tone": sanitize_text(campaign.campaign.tone, max_characters=500),
                "launch_date": campaign.campaign.launch_date,
                "promotion": sanitize_text(
                    campaign.campaign.promotion, max_characters=1000
                ),
                "raw_brief": self._optional_text(campaign.campaign.raw_brief, 20_000),
                "brief_analysis": self._safe_model(campaign.analysis, BriefAnalysis),
                "prior_generated_content": self._safe_optional_model(
                    campaign.generated_content, GeneratedContent
                ),
                "prior_quality_review": self._safe_optional_model(
                    campaign.quality_review, QualityReview
                ),
            }
        )
        await self.session.commit()
        return context

    async def build_content_review_context(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> ContentReviewContext:
        campaign, workflow = await self._load_pair(campaign_id, workflow_id)
        if campaign.analysis is None or campaign.generated_content is None:
            await self.session.rollback()
            raise AgentContextError(
                "Content review requires analysis and generated content"
            )
        context = ContentReviewContext.model_validate(
            {
                **self._workflow_fields(workflow),
                "campaign_objective": sanitize_text(
                    campaign.campaign.campaign_objective, max_characters=1000
                ),
                "platforms": tuple(campaign.campaign.platforms),
                "tone": sanitize_text(campaign.campaign.tone, max_characters=500),
                "brief_analysis": self._safe_model(campaign.analysis, BriefAnalysis),
                "generated_content": self._safe_model(
                    campaign.generated_content, GeneratedContent
                ),
                "prior_quality_review": self._safe_optional_model(
                    campaign.quality_review, QualityReview
                ),
            }
        )
        await self.session.commit()
        return context

    async def _load_pair(
        self, campaign_id: str, workflow_id: UUID
    ) -> tuple[CampaignRecord, WorkflowRun]:
        campaign = await self.campaigns.get_campaign(campaign_id)
        workflow = await self.workflows.get_workflow(workflow_id)
        if workflow.campaign_id != campaign_id:
            await self.session.rollback()
            raise AgentContextError("Workflow does not belong to campaign")
        return campaign, workflow

    def _workflow_fields(self, workflow: WorkflowRun) -> dict[str, object]:
        return {
            "campaign_id": workflow.campaign_id,
            "workflow_id": workflow.workflow_id,
            "revision_number": workflow.revision_number,
            "current_workflow_status": workflow.status,
            "retry_count": workflow.retry_count,
            "parent_workflow_id": workflow.parent_workflow_id,
        }

    def _safe_model(self, value: SchemaT, schema: type[SchemaT]) -> SchemaT:
        return schema.model_validate(sanitize_json(value.model_dump(mode="json")))

    def _safe_optional_model(
        self, value: SchemaT | None, schema: type[SchemaT]
    ) -> SchemaT | None:
        return self._safe_model(value, schema) if value is not None else None

    def _optional_text(self, value: str | None, limit: int) -> str | None:
        return sanitize_text(value, max_characters=limit) if value else None

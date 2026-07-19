from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CampaignStatus, WorkflowStep
from app.core.exceptions import (
    CampaignNotFoundError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)
from app.llm.base import LLMClient
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview
from app.schemas.workflow_run import WorkflowRun
from app.service.mappers import workflow_to_schema
from app.workflows.workflow_state import ensure_valid_transition


class CampaignWorkflow:
    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.settings = get_settings()
        self.campaign_repository = CampaignRepository(session)
        self.workflow_repository = WorkflowRepository(session)

    async def run_to_pending_approval(self, workflow_id: UUID) -> WorkflowRun:
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id_for_update(
            workflow.campaign_id
        )
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")

        try:
            await self._transition(
                workflow,
                campaign,
                CampaignStatus.VALIDATING,
                WorkflowStep.VALIDATE_INPUT,
            )
            await self._transition(
                workflow, campaign, CampaignStatus.ANALYZING, WorkflowStep.ANALYZE_BRIEF
            )
            analysis = await self._generate(
                "Analyze the campaign brief into the requested structured schema.",
                campaign.raw_brief or campaign.campaign_objective,
                BriefAnalysis,
                workflow,
            )
            await self.campaign_repository.save_brief_analysis(campaign, analysis)

            await self._transition(
                workflow,
                campaign,
                CampaignStatus.GENERATING,
                WorkflowStep.GENERATE_CONTENT,
            )
            content = await self._generate(
                "Generate platform-specific campaign content.",
                str(analysis.model_dump(mode="json")),
                GeneratedContent,
                workflow,
            )
            await self.campaign_repository.save_generated_content(campaign, content)

            await self._transition(
                workflow,
                campaign,
                CampaignStatus.REVIEWING,
                WorkflowStep.REVIEW_CONTENT,
            )
            review = await self._generate(
                "Review the generated content and return a quality review.",
                str(content.model_dump(mode="json")),
                QualityReview,
                workflow,
            )
            await self.campaign_repository.save_quality_review(campaign, review)
            await self.workflow_repository.save_quality_score(
                workflow, review.quality_score
            )

            if review.status == "MANUAL_REVIEW_REQUIRED":
                next_status = CampaignStatus.MANUAL_REVIEW_REQUIRED
                next_step = WorkflowStep.HUMAN_REVIEW
            elif review.status == "PASS":
                next_status = CampaignStatus.PENDING_APPROVAL
                next_step = WorkflowStep.HUMAN_REVIEW
            else:
                if workflow.retry_count >= self.settings.max_content_retries:
                    next_status = CampaignStatus.MANUAL_REVIEW_REQUIRED
                    next_step = WorkflowStep.HUMAN_REVIEW
                else:
                    await self.workflow_repository.increment_retry_count(workflow)
                    await self.campaign_repository.increment_retry_count(campaign)
                    next_status = CampaignStatus.GENERATING
                    next_step = WorkflowStep.GENERATE_CONTENT

            await self._transition(workflow, campaign, next_status, next_step)
            if next_status == CampaignStatus.MANUAL_REVIEW_REQUIRED:
                await self._transition(
                    workflow,
                    campaign,
                    CampaignStatus.PENDING_APPROVAL,
                    WorkflowStep.HUMAN_REVIEW,
                )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return workflow_to_schema(workflow)

    async def _transition(
        self,
        workflow,
        campaign,
        next_status: CampaignStatus,
        next_step: WorkflowStep,
    ) -> None:
        ensure_valid_transition(CampaignStatus(workflow.status), next_status)
        await self.workflow_repository.update_status(workflow, next_status)
        await self.workflow_repository.update_current_step(workflow, next_step)
        await self.campaign_repository.update_status(campaign, next_status)

    async def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema,
        workflow,
    ):
        if workflow.llm_call_count >= self.settings.max_llm_calls_per_workflow:
            raise WorkflowLimitError("LLM call budget exhausted")
        await self.workflow_repository.increment_llm_call_count(workflow)
        return await self.llm_client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
        )

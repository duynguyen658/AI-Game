from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CampaignStatus, WorkflowStep
from app.core.exceptions import (
    ApplicationError,
    CampaignNotFoundError,
    VersionConflictError,
    WorkflowExecutionError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)
from app.llm.base import LLMClient
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview
from app.schemas.workflow_run import WorkflowRun
from app.service.mappers import workflow_to_schema
from app.workflows.workflow_state import can_transition, ensure_valid_transition

logger = structlog.get_logger()

SECRET_REPLACEMENTS = (
    (
        re.compile(r"(postgresql\+asyncpg://)[^@\s]+@", re.IGNORECASE),
        r"\1[REDACTED]@",
    ),
    (
        re.compile(
            r"(api[_-]?key|authorization|password|secret|token)=\S+",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
        "Bearer [REDACTED]",
    ),
)


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow: WorkflowRun
    campaign_objective: str
    raw_brief: str | None
    brief_analysis: dict[str, Any] | None
    generated_content: dict[str, Any] | None


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
        try:
            while True:
                snapshot = await self._load_snapshot(workflow_id)
                status = snapshot.workflow.status

                if status in {
                    CampaignStatus.PENDING_APPROVAL,
                    CampaignStatus.MANUAL_REVIEW_REQUIRED,
                    CampaignStatus.APPROVED,
                    CampaignStatus.REJECTED,
                    CampaignStatus.FAILED,
                    CampaignStatus.NEEDS_CLARIFICATION,
                }:
                    return snapshot.workflow

                if status == CampaignStatus.RECEIVED:
                    await self._transition_checkpoint(
                        workflow_id,
                        expected_status=CampaignStatus.RECEIVED,
                        next_status=CampaignStatus.VALIDATING,
                        next_step=WorkflowStep.VALIDATE_INPUT,
                    )
                    continue

                if status == CampaignStatus.VALIDATING:
                    await self._transition_checkpoint(
                        workflow_id,
                        expected_status=CampaignStatus.VALIDATING,
                        next_status=CampaignStatus.ANALYZING,
                        next_step=WorkflowStep.ANALYZE_BRIEF,
                    )
                    continue

                if status == CampaignStatus.REVISION_REQUIRED:
                    await self._transition_checkpoint(
                        workflow_id,
                        expected_status=CampaignStatus.REVISION_REQUIRED,
                        next_status=CampaignStatus.GENERATING,
                        next_step=WorkflowStep.GENERATE_CONTENT,
                    )
                    continue

                if status == CampaignStatus.ANALYZING:
                    await self._reserve_llm_call(
                        workflow_id,
                        expected_status=CampaignStatus.ANALYZING,
                    )
                    analysis = await self._generate(
                        "Analyze the campaign brief into the requested structured schema.",
                        snapshot.raw_brief or snapshot.campaign_objective,
                        BriefAnalysis,
                    )
                    await self._save_analysis_checkpoint(workflow_id, analysis)
                    continue

                if status == CampaignStatus.GENERATING:
                    analysis_payload = snapshot.brief_analysis
                    if analysis_payload is None:
                        await self._transition_checkpoint(
                            workflow_id,
                            expected_status=CampaignStatus.GENERATING,
                            next_status=CampaignStatus.ANALYZING,
                            next_step=WorkflowStep.ANALYZE_BRIEF,
                        )
                        continue
                    await self._reserve_llm_call(
                        workflow_id,
                        expected_status=CampaignStatus.GENERATING,
                    )
                    content = await self._generate(
                        "Generate platform-specific campaign content.",
                        str(analysis_payload),
                        GeneratedContent,
                    )
                    await self._save_content_checkpoint(workflow_id, content)
                    continue

                if status == CampaignStatus.REVIEWING:
                    content_payload = snapshot.generated_content
                    if content_payload is None:
                        await self._transition_checkpoint(
                            workflow_id,
                            expected_status=CampaignStatus.REVIEWING,
                            next_status=CampaignStatus.GENERATING,
                            next_step=WorkflowStep.GENERATE_CONTENT,
                        )
                        continue
                    await self._reserve_llm_call(
                        workflow_id,
                        expected_status=CampaignStatus.REVIEWING,
                    )
                    review = await self._generate(
                        "Review the generated content and return a quality review.",
                        str(content_payload),
                        QualityReview,
                    )
                    await self._save_review_decision_checkpoint(workflow_id, review)
                    continue

                raise WorkflowExecutionError(
                    f"Workflow cannot resume from {status.value}"
                )
        except ApplicationError as exc:
            await self._persist_failure(workflow_id, exc)
            raise
        except Exception as exc:
            wrapped = WorkflowExecutionError("Workflow execution failed")
            await self._persist_failure(workflow_id, wrapped)
            raise wrapped from exc

    async def _load_snapshot(self, workflow_id: UUID) -> WorkflowSnapshot:
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id_for_update(
            workflow.campaign_id
        )
        if campaign is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        snapshot = WorkflowSnapshot(
            workflow=workflow_to_schema(workflow),
            campaign_objective=campaign.campaign_objective,
            raw_brief=campaign.raw_brief,
            brief_analysis=campaign.brief_analysis,
            generated_content=campaign.generated_content,
        )
        await self.session.commit()
        return snapshot

    async def _transition_checkpoint(
        self,
        workflow_id: UUID,
        *,
        expected_status: CampaignStatus,
        next_status: CampaignStatus,
        next_step: WorkflowStep,
    ) -> WorkflowRun:
        workflow, campaign = await self._load_locked_pair(workflow_id)
        self._ensure_expected_status(workflow.status, expected_status)
        ensure_valid_transition(expected_status, next_status)
        await self.workflow_repository.update_status(workflow, next_status)
        await self.workflow_repository.update_current_step(workflow, next_step)
        await self.campaign_repository.update_status(campaign, next_status)
        await self.session.commit()
        return workflow_to_schema(workflow)

    async def _reserve_llm_call(
        self,
        workflow_id: UUID,
        *,
        expected_status: CampaignStatus,
    ) -> None:
        workflow, _ = await self._load_locked_pair(workflow_id)
        self._ensure_expected_status(workflow.status, expected_status)
        if workflow.llm_call_count >= self.settings.max_llm_calls_per_workflow:
            await self.session.rollback()
            raise WorkflowLimitError("LLM call budget exhausted")
        await self.workflow_repository.increment_llm_call_count(workflow)
        await self.session.commit()

    async def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        return await self.llm_client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
        )

    async def _save_analysis_checkpoint(
        self,
        workflow_id: UUID,
        analysis: BaseModel,
    ) -> None:
        workflow, campaign = await self._load_locked_pair(workflow_id)
        self._ensure_expected_status(workflow.status, CampaignStatus.ANALYZING)
        await self.campaign_repository.save_brief_analysis(
            campaign,
            BriefAnalysis.model_validate(analysis),
        )
        await self._transition_locked(
            workflow,
            campaign,
            CampaignStatus.GENERATING,
            WorkflowStep.GENERATE_CONTENT,
        )
        await self.session.commit()

    async def _save_content_checkpoint(
        self,
        workflow_id: UUID,
        content: BaseModel,
    ) -> None:
        workflow, campaign = await self._load_locked_pair(workflow_id)
        self._ensure_expected_status(workflow.status, CampaignStatus.GENERATING)
        await self.campaign_repository.save_generated_content(
            campaign,
            GeneratedContent.model_validate(content),
        )
        await self._transition_locked(
            workflow,
            campaign,
            CampaignStatus.REVIEWING,
            WorkflowStep.REVIEW_CONTENT,
        )
        await self.session.commit()

    async def _save_review_decision_checkpoint(
        self,
        workflow_id: UUID,
        review: BaseModel,
    ) -> None:
        workflow, campaign = await self._load_locked_pair(workflow_id)
        self._ensure_expected_status(workflow.status, CampaignStatus.REVIEWING)
        quality_review = QualityReview.model_validate(review)
        await self.campaign_repository.save_quality_review(campaign, quality_review)
        await self.workflow_repository.save_quality_score(
            workflow,
            quality_review.quality_score,
        )

        if quality_review.status == "PASS":
            await self._transition_locked(
                workflow,
                campaign,
                CampaignStatus.PENDING_APPROVAL,
                WorkflowStep.HUMAN_REVIEW,
            )
        elif quality_review.status == "MANUAL_REVIEW_REQUIRED":
            await self._transition_locked(
                workflow,
                campaign,
                CampaignStatus.MANUAL_REVIEW_REQUIRED,
                WorkflowStep.HUMAN_REVIEW,
            )
        elif workflow.retry_count >= self.settings.max_content_retries:
            await self._transition_locked(
                workflow,
                campaign,
                CampaignStatus.MANUAL_REVIEW_REQUIRED,
                WorkflowStep.HUMAN_REVIEW,
            )
        else:
            await self.workflow_repository.increment_retry_count(workflow)
            await self.campaign_repository.increment_retry_count(campaign)
            await self._transition_locked(
                workflow,
                campaign,
                CampaignStatus.GENERATING,
                WorkflowStep.GENERATE_CONTENT,
            )
        await self.session.commit()

    async def _transition_locked(
        self,
        workflow,
        campaign,
        next_status: CampaignStatus,
        next_step: WorkflowStep,
    ) -> None:
        previous_status = CampaignStatus(workflow.status)
        ensure_valid_transition(previous_status, next_status)
        await self.workflow_repository.update_status(workflow, next_status)
        await self.workflow_repository.update_current_step(workflow, next_step)
        await self.campaign_repository.update_status(campaign, next_status)
        logger.info(
            "workflow_transition",
            campaign_id=campaign.campaign_id,
            workflow_id=str(workflow.workflow_id),
            previous_status=previous_status.value,
            next_status=next_status.value,
            current_step=next_step.value,
        )

    async def _load_locked_pair(self, workflow_id: UUID):
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id_for_update(
            workflow.campaign_id
        )
        if campaign is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        return workflow, campaign

    def _ensure_expected_status(
        self,
        actual_status: str,
        expected_status: CampaignStatus,
    ) -> None:
        if CampaignStatus(actual_status) != expected_status:
            raise VersionConflictError("Workflow state changed during execution")

    async def _persist_failure(
        self,
        workflow_id: UUID,
        exc: ApplicationError,
    ) -> None:
        await self.session.rollback()
        try:
            workflow, campaign = await self._load_locked_pair(workflow_id)
            current_status = CampaignStatus(workflow.status)
            if current_status in {
                CampaignStatus.APPROVED,
                CampaignStatus.REJECTED,
                CampaignStatus.FAILED,
                CampaignStatus.PENDING_APPROVAL,
                CampaignStatus.MANUAL_REVIEW_REQUIRED,
            }:
                await self.session.rollback()
                return
            if can_transition(current_status, CampaignStatus.FAILED):
                await self.workflow_repository.mark_failed(
                    workflow,
                    error_code=exc.error_code,
                    error_message=self._safe_error_message(exc.message),
                )
                await self.campaign_repository.update_status(
                    campaign,
                    CampaignStatus.FAILED,
                )
                await self.session.commit()
            else:
                await self.session.rollback()
        except Exception as failure_exc:
            await self.session.rollback()
            logger.error(
                "workflow_failure_persistence_failed",
                workflow_id=str(workflow_id),
                safe_exception_type=type(failure_exc).__name__,
            )

    def _safe_error_message(self, message: str) -> str:
        safe_message = message[:500]
        for pattern, replacement in SECRET_REPLACEMENTS:
            safe_message = pattern.sub(replacement, safe_message)
        return safe_message

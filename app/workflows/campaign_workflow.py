from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.runtime.orchestrator import AgenticOrchestrator
from app.core.config import get_settings
from app.core.constants import CampaignStatus, MemoryEventType, WorkflowStep
from app.core.exceptions import (
    ApplicationError,
    AgentExecutionError,
    ApprovalAlreadyDecidedError,
    ApprovalNotAllowedError,
    AuthenticationError,
    AuthorizationError,
    CampaignNotFoundError,
    InvalidStateTransitionError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
    VersionConflictError,
    WorkflowAlreadyActiveError,
    WorkflowCreationNotAllowedError,
    WorkflowExecutionError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)
from app.llm.base import LLMClient
from app.core.sanitization import sanitize_text
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview
from app.schemas.workflow_run import WorkflowRun
from app.service.mappers import workflow_to_schema
from app.service.memory_service import MemoryService
from app.workflows.workflow_state import can_transition, ensure_valid_transition

logger = structlog.get_logger()

CONFLICT_ERRORS = (
    ApprovalAlreadyDecidedError,
    ApprovalNotAllowedError,
    AuthenticationError,
    AuthorizationError,
    InvalidStateTransitionError,
    VersionConflictError,
    WorkflowAlreadyActiveError,
    WorkflowCreationNotAllowedError,
    WorkflowNotFoundError,
    CampaignNotFoundError,
)

EXECUTION_FAILURE_ERRORS = (
    AgentExecutionError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
    WorkflowExecutionError,
    WorkflowLimitError,
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
        orchestrator: AgenticOrchestrator | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.settings = get_settings()
        self.campaign_repository = CampaignRepository(session)
        self.workflow_repository = WorkflowRepository(session)
        self.orchestrator = orchestrator or AgenticOrchestrator(session, llm_client)
        self.memory_service = MemoryService(session)

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
                    analysis = await self.orchestrator.run_brief_analysis(
                        campaign_id=snapshot.workflow.campaign_id,
                        workflow_id=workflow_id,
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
                    content = await self.orchestrator.run_content_generation(
                        campaign_id=snapshot.workflow.campaign_id,
                        workflow_id=workflow_id,
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
                    review = await self.orchestrator.run_content_review(
                        campaign_id=snapshot.workflow.campaign_id,
                        workflow_id=workflow_id,
                    )
                    await self._save_review_decision_checkpoint(workflow_id, review)
                    continue

                raise WorkflowExecutionError(
                    f"Workflow cannot resume from {status.value}"
                )
        except CONFLICT_ERRORS:
            await self.session.rollback()
            raise
        except EXECUTION_FAILURE_ERRORS as exc:
            await self._persist_failure(workflow_id, exc)
            raise
        except Exception as exc:
            wrapped = WorkflowExecutionError("Workflow execution failed")
            await self._persist_failure(workflow_id, wrapped)
            raise wrapped from exc

    async def _load_snapshot(self, workflow_id: UUID) -> WorkflowSnapshot:
        # Snapshot reads intentionally avoid FOR UPDATE. LLM calls happen after this
        # read transaction is closed; write checkpoints reacquire Campaign -> Workflow.
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if workflow is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id(workflow.campaign_id)
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
        workflow_retry = False
        revision_completed = False

        if quality_review.status == "PASS":
            revision_completed = workflow.revision_number > 0
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
            workflow_retry = True
            await self.workflow_repository.increment_retry_count(workflow)
            await self.campaign_repository.increment_retry_count(campaign)
            await self._transition_locked(
                workflow,
                campaign,
                CampaignStatus.GENERATING,
                WorkflowStep.GENERATE_CONTENT,
            )
        await self.session.commit()
        await self.memory_service.record_event(
            campaign_id=campaign.campaign_id,
            workflow_id=workflow.workflow_id,
            event_type=MemoryEventType.REVIEW_FEEDBACK,
            summary=(
                "; ".join(quality_review.issues or quality_review.suggestions)
                or f"Review completed with status {quality_review.status}"
            ),
            metadata={
                "status": quality_review.status,
                "quality_score": quality_review.quality_score,
                "retry_count": workflow.retry_count,
            },
            importance=4,
        )
        if workflow_retry:
            await self.memory_service.record_event(
                campaign_id=campaign.campaign_id,
                workflow_id=workflow.workflow_id,
                event_type=MemoryEventType.WORKFLOW_RETRY,
                summary=(
                    "; ".join(quality_review.issues or quality_review.suggestions)
                    or "Review requested bounded content regeneration"
                ),
                metadata={"retry_count": workflow.retry_count},
                importance=4,
            )
        if revision_completed:
            await self.memory_service.record_event(
                campaign_id=campaign.campaign_id,
                workflow_id=workflow.workflow_id,
                event_type=MemoryEventType.REVISION_COMPLETED,
                summary="Revised campaign content passed review",
                metadata={
                    "revision_number": workflow.revision_number,
                    "quality_score": quality_review.quality_score,
                },
                importance=5,
            )

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
        # Lock order for every multi-row workflow transaction:
        # Campaign -> Workflow -> child rows. The initial unlocked read only discovers
        # the campaign_id needed to acquire locks in that order.
        workflow_hint = await self.workflow_repository.get_by_id(workflow_id)
        if workflow_hint is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id_for_update(
            workflow_hint.campaign_id
        )
        if campaign is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None or workflow.campaign_id != campaign.campaign_id:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
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
        return sanitize_text(message, max_characters=500)

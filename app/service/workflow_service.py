from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
import structlog

from app.core.constants import (
    WORKFLOW_CREATABLE_CAMPAIGN_STATUSES,
    CampaignStatus,
    WorkflowStep,
)
from app.core.exceptions import (
    CampaignNotFoundError,
    InvalidStateTransitionError,
    PersistenceError,
    WorkflowAlreadyActiveError,
    WorkflowCreationNotAllowedError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)
from app.database.integrity import get_constraint_name
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow_run import WorkflowRun
from app.service.mappers import workflow_to_schema
from app.workflows.workflow_state import ensure_valid_transition

logger = structlog.get_logger()


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repository = CampaignRepository(session)
        self.workflow_repository = WorkflowRepository(session)
        self.settings = get_settings()

    async def create_workflow(self, campaign_id: str) -> WorkflowRun:
        campaign = await self.campaign_repository.get_by_id_for_update(campaign_id)
        if campaign is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        campaign_status = CampaignStatus(campaign.status)
        if campaign_status not in WORKFLOW_CREATABLE_CAMPAIGN_STATUSES:
            await self.session.rollback()
            raise WorkflowCreationNotAllowedError(
                f"Cannot create workflow for campaign in {campaign_status.value}"
            )
        active = await self.workflow_repository.get_active_for_campaign(campaign_id)
        if active is not None:
            await self.session.rollback()
            raise WorkflowAlreadyActiveError("Campaign already has an active workflow")
        try:
            if campaign_status == CampaignStatus.REVISION_REQUIRED:
                parent = (
                    await self.workflow_repository.latest_revision_parent_for_campaign(
                        campaign_id
                    )
                )
                if parent is None:
                    await self.session.rollback()
                    raise WorkflowCreationNotAllowedError(
                        "Revision workflow requires a completed parent workflow"
                    )
                workflow = await self.workflow_repository.create(
                    campaign_id,
                    status=CampaignStatus.REVISION_REQUIRED,
                    current_step=WorkflowStep.HUMAN_REVIEW,
                    parent_workflow_id=parent.workflow_id,
                    revision_number=parent.revision_number + 1,
                    evaluation_run_id=campaign.evaluation_run_id,
                    evaluation_case_id=campaign.evaluation_case_id,
                )
            else:
                workflow = await self.workflow_repository.create(
                    campaign_id,
                    evaluation_run_id=campaign.evaluation_run_id,
                    evaluation_case_id=campaign.evaluation_case_id,
                )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            constraint_name = get_constraint_name(exc)
            logger.warning(
                "workflow_create_integrity_error",
                constraint_name=constraint_name,
                operation="create_workflow",
            )
            if constraint_name == "uq_workflow_runs_one_active_per_campaign":
                raise WorkflowAlreadyActiveError(
                    "Campaign already has an active workflow"
                ) from exc
            raise PersistenceError("Workflow could not be persisted") from exc
        return workflow_to_schema(workflow)

    async def get_workflow(self, workflow_id: UUID) -> WorkflowRun:
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        return workflow_to_schema(workflow)

    async def list_workflows(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        campaign_id: str | None = None,
        owner_id: str | None = None,
        reviewable_only: bool = False,
    ) -> list[WorkflowRun]:
        workflows = await self.workflow_repository.list_accessible(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            campaign_id=campaign_id,
            owner_id=owner_id,
            reviewable_only=reviewable_only,
        )
        return [workflow_to_schema(workflow) for workflow in workflows]

    async def transition(
        self,
        workflow_id: UUID,
        next_status: CampaignStatus,
        *,
        step: WorkflowStep | None = None,
    ) -> WorkflowRun:
        workflow_hint = await self.workflow_repository.get_by_id(workflow_id)
        if workflow_hint is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        campaign = await self.campaign_repository.get_by_id_for_update(
            workflow_hint.campaign_id
        )
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")
        workflow = await self.workflow_repository.get_by_id_for_update(workflow_id)
        if workflow is None or workflow.campaign_id != campaign.campaign_id:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        try:
            ensure_valid_transition(CampaignStatus(workflow.status), next_status)
        except InvalidStateTransitionError:
            await self.session.rollback()
            raise
        await self.workflow_repository.update_status(workflow, next_status)
        await self.campaign_repository.update_status(campaign, next_status)
        if step is not None:
            await self.workflow_repository.update_current_step(workflow, step)
        await self.session.commit()
        return workflow_to_schema(workflow)

    async def record_llm_call(self, workflow_id: UUID) -> None:
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
        if workflow.llm_call_count >= self.settings.max_llm_calls_per_workflow:
            await self.session.rollback()
            raise WorkflowLimitError("LLM call budget exhausted")
        await self.workflow_repository.increment_llm_call_count(workflow)
        await self.session.commit()

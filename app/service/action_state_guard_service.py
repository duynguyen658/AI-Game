from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.definitions import ActionExecutionGuard
from app.core.constants import CampaignStatus, WorkflowStep
from app.core.exceptions import (
    ActionScopeConflictError,
    ActionStateChangedError,
    InvalidStateTransitionError,
)
from app.database.models import CampaignModel, WorkflowRunModel
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.campaign import CampaignMetadataUpdate, CampaignRecord
from app.service.mappers import campaign_to_record
from app.workflows.workflow_state import ensure_valid_transition


class ActionStateGuardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)

    async def validate(self, guard: ActionExecutionGuard) -> CampaignRecord:
        campaign, _ = await self._locked_pair(guard)
        result = campaign_to_record(campaign)
        await self.session.commit()
        return result

    async def update_metadata(
        self,
        guard: ActionExecutionGuard,
        payload: CampaignMetadataUpdate,
    ) -> None:
        campaign, _ = await self._locked_pair(guard)
        await self.campaigns.update_metadata(campaign, payload)
        await self.campaigns.increment_version(campaign)
        await self.session.commit()

    async def transition(
        self,
        guard: ActionExecutionGuard,
        next_status: CampaignStatus,
        *,
        step: WorkflowStep,
    ) -> None:
        campaign, workflow = await self._locked_pair(guard)
        try:
            ensure_valid_transition(CampaignStatus(workflow.status), next_status)
        except InvalidStateTransitionError as exc:
            await self.session.rollback()
            raise ActionStateChangedError(
                "Reserved workflow transition is no longer valid"
            ) from exc
        await self.workflows.update_status(workflow, next_status)
        await self.workflows.update_current_step(workflow, step)
        await self.campaigns.update_status(campaign, next_status)
        await self.session.commit()

    async def _locked_pair(
        self, guard: ActionExecutionGuard
    ) -> tuple[CampaignModel, WorkflowRunModel]:
        await self.session.rollback()
        campaign = await self.campaigns.get_by_id_for_update(guard.campaign_id)
        if campaign is None:
            await self.session.rollback()
            raise ActionScopeConflictError("Reserved campaign scope is unavailable")
        workflow = await self.workflows.get_by_id_for_update(guard.workflow_id)
        if workflow is None or workflow.campaign_id != campaign.campaign_id:
            await self.session.rollback()
            raise ActionScopeConflictError("Reserved workflow scope is invalid")
        if (
            campaign.status != guard.expected_campaign_status.value
            or campaign.version != guard.expected_campaign_version
            or workflow.status != guard.expected_workflow_status.value
            or workflow.revision_number != guard.expected_revision_number
        ):
            await self.session.rollback()
            raise ActionStateChangedError(
                "Campaign or workflow changed after action reservation"
            )
        return campaign, workflow

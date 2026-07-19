from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalDecision, CampaignStatus, UserRole
from app.core.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotAllowedError,
    CampaignNotFoundError,
    VersionConflictError,
    WorkflowNotFoundError,
)
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.approval import ApprovalRecord, ApprovalRequest
from app.service.mappers import approval_to_schema
from app.workflows.workflow_state import ensure_valid_transition

APPROVER_ROLES = {UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN}


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repository = CampaignRepository(session)
        self.workflow_repository = WorkflowRepository(session)
        self.approval_repository = ApprovalRepository(session)

    async def decide(
        self,
        request: ApprovalRequest,
        *,
        actor_id: str,
        actor_role: UserRole,
    ) -> ApprovalRecord:
        if actor_role not in APPROVER_ROLES:
            raise ApprovalNotAllowedError("Actor is not allowed to decide approvals")
        campaign = await self.campaign_repository.get_by_id_for_update(
            request.campaign_id
        )
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")
        workflow = await self.workflow_repository.get_by_id_for_update(
            request.workflow_id
        )
        if workflow is None or workflow.campaign_id != request.campaign_id:
            raise WorkflowNotFoundError("Workflow not found")
        if CampaignStatus(workflow.status) != CampaignStatus.PENDING_APPROVAL:
            raise ApprovalNotAllowedError("Workflow is not pending approval")
        if campaign.version != request.expected_version:
            raise VersionConflictError("Campaign version does not match")
        if await self.approval_repository.has_final_decision(request.workflow_id):
            raise ApprovalAlreadyDecidedError(
                "Workflow already has an approval decision"
            )

        previous_version = campaign.version
        resulting_version = previous_version
        if request.decision == ApprovalDecision.APPROVE:
            next_status = CampaignStatus.APPROVED
        elif request.decision == ApprovalDecision.REJECT:
            next_status = CampaignStatus.REJECTED
        else:
            next_status = CampaignStatus.REVISION_REQUIRED
            await self.campaign_repository.increment_version(campaign)
            resulting_version = campaign.version

        ensure_valid_transition(CampaignStatus(workflow.status), next_status)
        await self.workflow_repository.update_status(workflow, next_status)
        await self.campaign_repository.update_status(campaign, next_status)
        await self.workflow_repository.mark_completed(workflow)

        record = await self.approval_repository.create(
            ApprovalRecord(
                campaign_id=request.campaign_id,
                workflow_id=request.workflow_id,
                decision=request.decision,
                feedback=request.feedback,
                actor_id=actor_id,
                actor_role=actor_role,
                previous_version=previous_version,
                resulting_version=resulting_version,
            )
        )
        await self.session.commit()
        return approval_to_schema(record)

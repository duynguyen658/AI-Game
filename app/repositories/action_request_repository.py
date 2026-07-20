from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ActionRequestStatus
from app.database.models import AgentActionRequestModel
from app.schemas.action_request import ActionRequestCreate
from app.schemas.policy_decision import PolicyEvaluationContext, PolicyEvaluationResult


class ActionRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_proposal(
        self,
        payload: ActionRequestCreate,
        policy: PolicyEvaluationResult,
        context: PolicyEvaluationContext,
        *,
        status: ActionRequestStatus,
        expires_at: datetime | None = None,
        rejected_at: datetime | None = None,
        rejection_reason: str | None = None,
    ) -> AgentActionRequestModel:
        model = AgentActionRequestModel(
            **payload.model_dump(mode="python"),
            policy_decision=policy.decision.value,
            policy_reason_code=policy.reason_code,
            policy_reason=policy.reason,
            required_role=policy.required_role.value if policy.required_role else None,
            last_policy_decision=policy.decision.value,
            last_policy_reason_code=policy.reason_code,
            last_policy_reason=policy.reason,
            last_required_role=(
                policy.required_role.value if policy.required_role else None
            ),
            last_policy_campaign_status=context.campaign_status.value,
            last_policy_workflow_status=context.workflow_status.value,
            last_policy_revision_number=context.revision_number,
            last_policy_evaluated_at=datetime.now(UTC),
            status=status.value,
            expires_at=expires_at,
            rejected_at=rejected_at,
            rejection_reason=rejection_reason,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(
        self, action_request_id: UUID
    ) -> AgentActionRequestModel | None:
        return await self.session.get(AgentActionRequestModel, action_request_id)

    async def get_by_id_for_update(
        self, action_request_id: UUID
    ) -> AgentActionRequestModel | None:
        result = await self.session.execute(
            select(AgentActionRequestModel)
            .where(AgentActionRequestModel.action_request_id == action_request_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self, idempotency_key: str
    ) -> AgentActionRequestModel | None:
        result = await self.session.execute(
            select(AgentActionRequestModel).where(
                AgentActionRequestModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        campaign_id: str | None = None,
        workflow_id: UUID | None = None,
        status: ActionRequestStatus | None = None,
    ) -> Sequence[AgentActionRequestModel]:
        query: Select[tuple[AgentActionRequestModel]] = select(AgentActionRequestModel)
        if campaign_id is not None:
            query = query.where(AgentActionRequestModel.campaign_id == campaign_id)
        if workflow_id is not None:
            query = query.where(AgentActionRequestModel.workflow_id == workflow_id)
        if status is not None:
            query = query.where(AgentActionRequestModel.status == status.value)
        result = await self.session.execute(
            query.order_by(
                AgentActionRequestModel.requested_at.desc(),
                AgentActionRequestModel.action_request_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def list_by_campaign(
        self, campaign_id: str, *, limit: int, offset: int
    ) -> Sequence[AgentActionRequestModel]:
        return await self.list(campaign_id=campaign_id, limit=limit, offset=offset)

    async def list_by_workflow(
        self, workflow_id: UUID, *, limit: int, offset: int
    ) -> Sequence[AgentActionRequestModel]:
        return await self.list(workflow_id=workflow_id, limit=limit, offset=offset)

    async def list_pending_approval(
        self, *, limit: int, offset: int
    ) -> Sequence[AgentActionRequestModel]:
        return await self.list(
            status=ActionRequestStatus.PENDING_APPROVAL,
            limit=limit,
            offset=offset,
        )

    async def save_latest_policy_result(
        self,
        request: AgentActionRequestModel,
        policy: PolicyEvaluationResult,
        context: PolicyEvaluationContext,
        *,
        reason_code: str | None = None,
        reason: str | None = None,
    ) -> AgentActionRequestModel:
        request.last_policy_decision = policy.decision.value
        request.last_policy_reason_code = reason_code or policy.reason_code
        request.last_policy_reason = reason or policy.reason
        request.last_required_role = (
            policy.required_role.value if policy.required_role else None
        )
        request.last_policy_campaign_status = context.campaign_status.value
        request.last_policy_workflow_status = context.workflow_status.value
        request.last_policy_revision_number = context.revision_number
        request.last_policy_evaluated_at = datetime.now(UTC)
        await self.session.flush()
        return request

    async def reject_after_policy_reevaluation(
        self,
        request: AgentActionRequestModel,
        *,
        reason: str,
    ) -> AgentActionRequestModel:
        now = datetime.now(UTC)
        request.status = ActionRequestStatus.REJECTED.value
        request.rejected_at = now
        request.rejection_reason = reason
        request.version += 1
        await self.session.flush()
        return request

    async def mark_pending_approval(
        self, request: AgentActionRequestModel, expires_at: datetime
    ) -> AgentActionRequestModel:
        request.status = ActionRequestStatus.PENDING_APPROVAL.value
        request.expires_at = expires_at
        request.version += 1
        await self.session.flush()
        return request

    async def approve(
        self,
        action_request_id: UUID,
        *,
        actor_id: str,
        actor_role: str,
        expected_version: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentActionRequestModel)
            .where(
                AgentActionRequestModel.action_request_id == action_request_id,
                AgentActionRequestModel.version == expected_version,
                AgentActionRequestModel.status
                == ActionRequestStatus.PENDING_APPROVAL.value,
            )
            .values(
                status=ActionRequestStatus.APPROVED.value,
                approved_by=actor_id,
                approved_role=actor_role,
                approved_at=now,
                version=AgentActionRequestModel.version + 1,
                updated_at=now,
            )
            .returning(AgentActionRequestModel.action_request_id)
        )
        return result.scalar_one_or_none() is not None

    async def reject(
        self,
        action_request_id: UUID,
        *,
        actor_id: str,
        reason: str,
        expected_version: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentActionRequestModel)
            .where(
                AgentActionRequestModel.action_request_id == action_request_id,
                AgentActionRequestModel.version == expected_version,
                AgentActionRequestModel.status.in_(
                    [
                        ActionRequestStatus.PROPOSED.value,
                        ActionRequestStatus.PENDING_APPROVAL.value,
                    ]
                ),
            )
            .values(
                status=ActionRequestStatus.REJECTED.value,
                rejected_by=actor_id,
                rejected_at=now,
                rejection_reason=reason,
                version=AgentActionRequestModel.version + 1,
                updated_at=now,
            )
            .returning(AgentActionRequestModel.action_request_id)
        )
        return result.scalar_one_or_none() is not None

    async def expire(self, action_request_id: UUID, *, expected_version: int) -> bool:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentActionRequestModel)
            .where(
                AgentActionRequestModel.action_request_id == action_request_id,
                AgentActionRequestModel.version == expected_version,
                AgentActionRequestModel.status.in_(
                    [
                        ActionRequestStatus.PENDING_APPROVAL.value,
                        ActionRequestStatus.APPROVED.value,
                    ]
                ),
            )
            .values(
                status=ActionRequestStatus.EXPIRED.value,
                version=AgentActionRequestModel.version + 1,
                updated_at=now,
            )
            .returning(AgentActionRequestModel.action_request_id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_executing(
        self, request: AgentActionRequestModel
    ) -> AgentActionRequestModel:
        request.status = ActionRequestStatus.EXECUTING.value
        request.version += 1
        await self.session.flush()
        return request

    async def mark_completed(
        self, request: AgentActionRequestModel
    ) -> AgentActionRequestModel:
        request.status = ActionRequestStatus.COMPLETED.value
        request.version += 1
        await self.session.flush()
        return request

    async def mark_failed(
        self, request: AgentActionRequestModel
    ) -> AgentActionRequestModel:
        request.status = ActionRequestStatus.FAILED.value
        request.version += 1
        await self.session.flush()
        return request

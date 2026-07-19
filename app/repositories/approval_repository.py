from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ApprovalRecordModel
from app.schemas.approval import ApprovalRecord


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ApprovalRecord) -> ApprovalRecordModel:
        model = ApprovalRecordModel(
            campaign_id=payload.campaign_id,
            workflow_id=payload.workflow_id,
            decision=payload.decision.value,
            feedback=payload.feedback,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            previous_version=payload.previous_version,
            resulting_version=payload.resulting_version,
            decided_at=payload.decided_at,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def list_workflow_history(
        self,
        workflow_id: UUID,
    ) -> Sequence[ApprovalRecordModel]:
        result = await self.session.execute(
            select(ApprovalRecordModel)
            .where(ApprovalRecordModel.workflow_id == workflow_id)
            .order_by(ApprovalRecordModel.decided_at.asc())
        )
        return result.scalars().all()

    async def latest_for_workflow(
        self,
        workflow_id: UUID,
    ) -> ApprovalRecordModel | None:
        result = await self.session.execute(
            select(ApprovalRecordModel)
            .where(ApprovalRecordModel.workflow_id == workflow_id)
            .order_by(ApprovalRecordModel.decided_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_final_decision(self, workflow_id: UUID) -> bool:
        latest = await self.latest_for_workflow(workflow_id)
        return latest is not None

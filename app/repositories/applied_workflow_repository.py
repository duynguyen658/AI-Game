from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppliedWorkflowTaskModel


class AppliedWorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, model: AppliedWorkflowTaskModel) -> AppliedWorkflowTaskModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get(self, task_run_id: UUID) -> AppliedWorkflowTaskModel | None:
        return await self.session.get(AppliedWorkflowTaskModel, task_run_id)

    async def get_for_update(
        self, task_run_id: UUID
    ) -> AppliedWorkflowTaskModel | None:
        return await self.session.scalar(
            select(AppliedWorkflowTaskModel)
            .where(AppliedWorkflowTaskModel.task_run_id == task_run_id)
            .with_for_update()
        )

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        owner_id: str | None = None,
        workflow_type: str | None = None,
        status: str | None = None,
    ) -> list[AppliedWorkflowTaskModel]:
        statement: Select[tuple[AppliedWorkflowTaskModel]] = select(
            AppliedWorkflowTaskModel
        )
        if owner_id is not None:
            statement = statement.where(AppliedWorkflowTaskModel.created_by == owner_id)
        if workflow_type is not None:
            statement = statement.where(
                AppliedWorkflowTaskModel.workflow_type == workflow_type
            )
        if status is not None:
            statement = statement.where(AppliedWorkflowTaskModel.status == status)
        result = await self.session.execute(
            statement.order_by(
                AppliedWorkflowTaskModel.created_at.desc(),
                AppliedWorkflowTaskModel.task_run_id,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
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

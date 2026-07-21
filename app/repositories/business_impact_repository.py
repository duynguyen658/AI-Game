from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AITaskImpactModel, TaskBaselineModel


class BusinessImpactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_baseline(self, model: TaskBaselineModel) -> TaskBaselineModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def list_baselines(
        self, *, limit: int, offset: int
    ) -> Sequence[TaskBaselineModel]:
        result = await self.session.execute(
            select(TaskBaselineModel)
            .order_by(TaskBaselineModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def create_impact(self, model: AITaskImpactModel) -> AITaskImpactModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_impact_by_task(self, task_run_id: UUID) -> AITaskImpactModel | None:
        return await self.session.scalar(
            select(AITaskImpactModel).where(
                AITaskImpactModel.task_run_id == task_run_id
            )
        )

    async def list_impacts(
        self,
        *,
        task_type: str | None = None,
        department: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        prompt_version_id: UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Sequence[AITaskImpactModel]:
        query: Select[tuple[AITaskImpactModel]] = select(AITaskImpactModel)
        filters = {
            AITaskImpactModel.task_type: task_type,
            AITaskImpactModel.department: department,
            AITaskImpactModel.provider: provider,
            AITaskImpactModel.model: model,
            AITaskImpactModel.prompt_version_id: prompt_version_id,
        }
        for column, value in filters.items():
            if value is not None:
                query = query.where(column == value)
        if created_from is not None:
            query = query.where(AITaskImpactModel.created_at >= created_from)
        if created_to is not None:
            query = query.where(AITaskImpactModel.created_at <= created_to)
        result = await self.session.execute(
            query.order_by(AITaskImpactModel.created_at)
        )
        return result.scalars().all()

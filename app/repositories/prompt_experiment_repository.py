from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PromptExperimentModel, PromptExperimentResultModel


class PromptExperimentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, model: PromptExperimentModel) -> PromptExperimentModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get(self, experiment_id: UUID) -> PromptExperimentModel | None:
        return await self.session.get(PromptExperimentModel, experiment_id)

    async def list(self, *, limit: int, offset: int) -> Sequence[PromptExperimentModel]:
        result = await self.session.execute(
            select(PromptExperimentModel)
            .order_by(PromptExperimentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def result(self, experiment_id: UUID) -> PromptExperimentResultModel | None:
        return await self.session.scalar(
            select(PromptExperimentResultModel).where(
                PromptExperimentResultModel.experiment_id == experiment_id
            )
        )

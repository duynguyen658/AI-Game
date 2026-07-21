from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ProviderComparisonCaseResultModel,
    ProviderComparisonModel,
)


class ProviderComparisonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, model: ProviderComparisonModel) -> ProviderComparisonModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get(self, comparison_id: UUID) -> ProviderComparisonModel | None:
        return await self.session.get(ProviderComparisonModel, comparison_id)

    async def get_for_update(
        self, comparison_id: UUID
    ) -> ProviderComparisonModel | None:
        return await self.session.scalar(
            select(ProviderComparisonModel)
            .where(ProviderComparisonModel.comparison_id == comparison_id)
            .with_for_update()
        )

    async def case_results(
        self, comparison_id: UUID
    ) -> Sequence[ProviderComparisonCaseResultModel]:
        result = await self.session.execute(
            select(ProviderComparisonCaseResultModel)
            .where(ProviderComparisonCaseResultModel.comparison_id == comparison_id)
            .order_by(
                ProviderComparisonCaseResultModel.provider,
                ProviderComparisonCaseResultModel.evaluation_case_id,
            )
        )
        return result.scalars().all()

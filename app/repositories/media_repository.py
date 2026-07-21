from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    MediaAssetModel,
    MediaGenerationAttemptModel,
    MediaReviewModel,
)


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_asset(self, model: MediaAssetModel) -> MediaAssetModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_asset(self, asset_id: UUID) -> MediaAssetModel | None:
        return await self.session.get(MediaAssetModel, asset_id)

    async def get_asset_for_update(self, asset_id: UUID) -> MediaAssetModel | None:
        return await self.session.scalar(
            select(MediaAssetModel)
            .where(MediaAssetModel.media_asset_id == asset_id)
            .with_for_update()
        )

    async def get_asset_by_idempotency(
        self, actor_id: str, idempotency_key: str
    ) -> MediaAssetModel | None:
        return await self.session.scalar(
            select(MediaAssetModel).where(
                MediaAssetModel.created_by == actor_id,
                MediaAssetModel.idempotency_key == idempotency_key,
            )
        )

    async def create_attempt(
        self, model: MediaGenerationAttemptModel
    ) -> MediaGenerationAttemptModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def next_attempt_number(self, asset_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(MediaGenerationAttemptModel.attempt_number)).where(
                MediaGenerationAttemptModel.media_asset_id == asset_id
            )
        )
        return int(current or 0) + 1

    async def get_attempt(self, attempt_id: UUID) -> MediaGenerationAttemptModel | None:
        return await self.session.get(MediaGenerationAttemptModel, attempt_id)

    async def create_review(self, model: MediaReviewModel) -> MediaReviewModel:
        self.session.add(model)
        await self.session.flush()
        return model

from __future__ import annotations

from uuid import UUID

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

    async def create_attempt(
        self, model: MediaGenerationAttemptModel
    ) -> MediaGenerationAttemptModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def create_review(self, model: MediaReviewModel) -> MediaReviewModel:
        self.session.add(model)
        await self.session.flush()
        return model

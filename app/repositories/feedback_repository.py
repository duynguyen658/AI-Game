from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserFeedbackModel


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_actor(
        self, task_run_id: UUID, actor_id: str
    ) -> UserFeedbackModel | None:
        return await self.session.scalar(
            select(UserFeedbackModel).where(
                UserFeedbackModel.task_run_id == task_run_id,
                UserFeedbackModel.actor_id == actor_id,
            )
        )

    async def create(self, model: UserFeedbackModel) -> UserFeedbackModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def list_feedback(
        self,
        *,
        task_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        prompt_version_id: UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Sequence[UserFeedbackModel]:
        statement = select(UserFeedbackModel)
        filters = {
            UserFeedbackModel.task_type: task_type,
            UserFeedbackModel.provider: provider,
            UserFeedbackModel.model: model,
            UserFeedbackModel.prompt_version_id: prompt_version_id,
        }
        for column, value in filters.items():
            if value is not None:
                statement = statement.where(column == value)
        if created_from is not None:
            statement = statement.where(UserFeedbackModel.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(UserFeedbackModel.created_at <= created_to)
        result = await self.session.execute(statement)
        return result.scalars().all()

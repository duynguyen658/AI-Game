from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PromptTemplateModel, PromptVersionModel


class PromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_template(self, model: PromptTemplateModel) -> PromptTemplateModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_template(self, template_id: UUID) -> PromptTemplateModel | None:
        return await self.session.get(PromptTemplateModel, template_id)

    async def get_template_for_update(
        self, template_id: UUID
    ) -> PromptTemplateModel | None:
        return await self.session.scalar(
            select(PromptTemplateModel)
            .where(PromptTemplateModel.prompt_template_id == template_id)
            .with_for_update()
        )

    async def get_template_by_slug(self, slug: str) -> PromptTemplateModel | None:
        return await self.session.scalar(
            select(PromptTemplateModel).where(PromptTemplateModel.slug == slug)
        )

    async def find_template(
        self, *, agent_name: str | None = None, task_type: str | None = None
    ) -> PromptTemplateModel | None:
        query = select(PromptTemplateModel).where(
            PromptTemplateModel.status == "ACTIVE"
        )
        if agent_name is not None:
            query = query.where(PromptTemplateModel.agent_name == agent_name)
        elif task_type is not None:
            query = query.where(PromptTemplateModel.task_type == task_type)
        else:
            return None
        return await self.session.scalar(query.order_by(PromptTemplateModel.created_at))

    async def list_templates(
        self, *, limit: int, offset: int
    ) -> Sequence[PromptTemplateModel]:
        result = await self.session.execute(
            select(PromptTemplateModel)
            .order_by(PromptTemplateModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def next_version(self, template_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(PromptVersionModel.version)).where(
                PromptVersionModel.prompt_template_id == template_id
            )
        )
        return int(current or 0) + 1

    async def create_version(self, model: PromptVersionModel) -> PromptVersionModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_version(self, version_id: UUID) -> PromptVersionModel | None:
        return await self.session.get(PromptVersionModel, version_id)

    async def get_active_version(self, template_id: UUID) -> PromptVersionModel | None:
        return await self.session.scalar(
            select(PromptVersionModel).where(
                PromptVersionModel.prompt_template_id == template_id,
                PromptVersionModel.status == "ACTIVE",
            )
        )

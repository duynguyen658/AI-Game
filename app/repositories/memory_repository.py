from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MemoryEventType
from app.database.models import AgentMemoryEntryModel
from app.schemas.memory_entry import MemoryEntryCreate


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: MemoryEntryCreate) -> AgentMemoryEntryModel:
        model = AgentMemoryEntryModel(
            **payload.model_dump(mode="python", by_alias=True, exclude={"metadata"}),
            metadata_=payload.metadata,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(self, memory_entry_id: UUID) -> AgentMemoryEntryModel | None:
        return await self.session.get(AgentMemoryEntryModel, memory_entry_id)

    async def find_by_execution_event(
        self, action_execution_id: UUID, event_type: MemoryEventType
    ) -> AgentMemoryEntryModel | None:
        result = await self.session.execute(
            select(AgentMemoryEntryModel).where(
                AgentMemoryEntryModel.action_execution_id == action_execution_id,
                AgentMemoryEntryModel.event_type == event_type.value,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        campaign_id: str | None = None,
        workflow_id: UUID | None = None,
        event_type: MemoryEventType | None = None,
        minimum_importance: int | None = None,
        non_expired: bool = True,
    ) -> Sequence[AgentMemoryEntryModel]:
        query: Select[tuple[AgentMemoryEntryModel]] = select(AgentMemoryEntryModel)
        if campaign_id is not None:
            query = query.where(AgentMemoryEntryModel.campaign_id == campaign_id)
        if workflow_id is not None:
            query = query.where(AgentMemoryEntryModel.workflow_id == workflow_id)
        if event_type is not None:
            query = query.where(AgentMemoryEntryModel.event_type == event_type.value)
        if minimum_importance is not None:
            query = query.where(AgentMemoryEntryModel.importance >= minimum_importance)
        if non_expired:
            now = datetime.now(UTC)
            query = query.where(
                or_(
                    AgentMemoryEntryModel.expires_at.is_(None),
                    AgentMemoryEntryModel.expires_at > now,
                )
            )
        result = await self.session.execute(
            query.order_by(
                AgentMemoryEntryModel.created_at.desc(),
                AgentMemoryEntryModel.memory_entry_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def list_by_campaign(
        self, campaign_id: str, *, limit: int, offset: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(campaign_id=campaign_id, limit=limit, offset=offset)

    async def list_by_workflow(
        self, workflow_id: UUID, *, limit: int, offset: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(workflow_id=workflow_id, limit=limit, offset=offset)

    async def list_by_event_type(
        self, event_type: MemoryEventType, *, limit: int, offset: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(event_type=event_type, limit=limit, offset=offset)

    async def list_recent(
        self, campaign_id: str, *, limit: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(campaign_id=campaign_id, limit=limit, offset=0)

    async def list_by_importance(
        self, campaign_id: str, *, minimum: int, limit: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(
            campaign_id=campaign_id,
            minimum_importance=minimum,
            limit=limit,
            offset=0,
        )

    async def list_non_expired(
        self, campaign_id: str, *, limit: int, offset: int
    ) -> Sequence[AgentMemoryEntryModel]:
        return await self.list(
            campaign_id=campaign_id,
            limit=limit,
            offset=offset,
            non_expired=True,
        )

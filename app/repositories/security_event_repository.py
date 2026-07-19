from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SecurityEventType
from app.database.models import SecurityEventModel
from app.schemas.security_event import SecurityEvent


class SecurityEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: SecurityEvent) -> SecurityEventModel:
        model = SecurityEventModel(
            event_id=payload.event_id,
            event_type=payload.event_type.value,
            severity=payload.severity.value,
            actor_id=payload.actor_id,
            campaign_id=payload.campaign_id,
            workflow_id=payload.workflow_id,
            source=payload.source,
            message=payload.message,
            metadata_=payload.metadata,
            created_at=payload.occurred_at,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        event_type: SecurityEventType | None = None,
        actor_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Sequence[SecurityEventModel]:
        query: Select[tuple[SecurityEventModel]] = select(SecurityEventModel)
        if event_type is not None:
            query = query.where(SecurityEventModel.event_type == event_type.value)
        if actor_id is not None:
            query = query.where(SecurityEventModel.actor_id == actor_id)
        if created_from is not None:
            query = query.where(SecurityEventModel.created_at >= created_from)
        if created_to is not None:
            query = query.where(SecurityEventModel.created_at <= created_to)
        result = await self.session.execute(
            query.order_by(SecurityEventModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

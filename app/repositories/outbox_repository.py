from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OutboxEventType, OutboxStatus
from app.core.exceptions import JobConflictError
from app.database.models import OutboxEventModel
from app.jobs.retry import retry_delay_seconds


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        idempotency_key: str,
        correlation_id: str,
        trace_id: str | None,
        max_attempts: int,
    ) -> OutboxEventModel:
        model = OutboxEventModel(
            event_type=event_type.value,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            trace_id=trace_id,
            max_attempts=max_attempts,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def find_by_key(self, idempotency_key: str) -> OutboxEventModel | None:
        result = await self.session.execute(
            select(OutboxEventModel).where(
                OutboxEventModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def lease_batch(
        self, *, worker_id: str, limit: int
    ) -> Sequence[OutboxEventModel]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(OutboxEventModel)
            .where(
                OutboxEventModel.status.in_(
                    [OutboxStatus.PENDING.value, OutboxStatus.FAILED.value]
                ),
                OutboxEventModel.available_at <= now,
            )
            .order_by(OutboxEventModel.available_at, OutboxEventModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()
        for event in events:
            event.status = OutboxStatus.PROCESSING.value
            event.locked_by = worker_id
            event.locked_at = now
            event.attempt_count += 1
        await self.session.flush()
        return events

    async def mark_processed(
        self, event_id: UUID, *, worker_id: str
    ) -> OutboxEventModel:
        event = await self._owned_for_update(event_id, worker_id)
        event.status = OutboxStatus.PROCESSED.value
        event.processed_at = datetime.now(UTC)
        event.locked_by = None
        event.locked_at = None
        event.error_code = None
        event.error_message = None
        await self.session.flush()
        return event

    async def mark_failed(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        error_code: str,
        error_message: str,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> OutboxEventModel:
        event = await self._owned_for_update(event_id, worker_id)
        event.error_code = error_code
        event.error_message = error_message
        if event.attempt_count >= event.max_attempts:
            event.status = OutboxStatus.DEAD_LETTER.value
        else:
            event.status = OutboxStatus.FAILED.value
            event.available_at = datetime.now(UTC) + timedelta(
                seconds=retry_delay_seconds(
                    event.attempt_count,
                    base_seconds=retry_base_seconds,
                    maximum_seconds=retry_max_seconds,
                )
            )
        event.locked_by = None
        event.locked_at = None
        await self.session.flush()
        return event

    async def reconcile_stale(
        self,
        *,
        older_than: datetime,
        limit: int,
    ) -> Sequence[OutboxEventModel]:
        result = await self.session.execute(
            select(OutboxEventModel)
            .where(
                OutboxEventModel.status == OutboxStatus.PROCESSING.value,
                OutboxEventModel.locked_at <= older_than,
            )
            .order_by(OutboxEventModel.locked_at, OutboxEventModel.outbox_event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()
        for event in events:
            event.status = (
                OutboxStatus.DEAD_LETTER.value
                if event.attempt_count >= event.max_attempts
                else OutboxStatus.FAILED.value
            )
            event.available_at = datetime.now(UTC)
            event.locked_by = None
            event.locked_at = None
            event.error_code = "OUTBOX_LEASE_EXPIRED"
            event.error_message = "Outbox consumer lease expired"
        await self.session.flush()
        return events

    async def _owned_for_update(
        self, event_id: UUID, worker_id: str
    ) -> OutboxEventModel:
        result = await self.session.execute(
            select(OutboxEventModel)
            .where(OutboxEventModel.outbox_event_id == event_id)
            .with_for_update()
        )
        event = result.scalar_one_or_none()
        if (
            event is None
            or event.status != OutboxStatus.PROCESSING.value
            or event.locked_by != worker_id
        ):
            raise JobConflictError("Outbox event is no longer owned by this consumer")
        return event

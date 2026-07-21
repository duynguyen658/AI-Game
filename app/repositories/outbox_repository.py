from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.constants import LeaseUpdateResult, OutboxEventType, OutboxStatus
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
        self, *, worker_id: str, limit: int, lease_seconds: int
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
            event.last_heartbeat_at = now
            event.lease_expires_at = now + timedelta(seconds=lease_seconds)
            event.lease_version += 1
            event.attempt_count += 1
        await self.session.flush()
        return events

    async def mark_processed(
        self, event_id: UUID, *, worker_id: str, lease_version: int
    ) -> LeaseUpdateResult:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(OutboxEventModel)
            .where(self._lease_condition(event_id, worker_id, lease_version, now))
            .values(
                status=OutboxStatus.PROCESSED.value,
                processed_at=now,
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                last_heartbeat_at=None,
                error_code=None,
                error_message=None,
            )
            .returning(OutboxEventModel.outbox_event_id)
        )
        if result.scalar_one_or_none() is not None:
            return LeaseUpdateResult.UPDATED
        return await self._classify_lease_failure(event_id)

    async def mark_failed(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        lease_version: int,
        attempt_count: int,
        max_attempts: int,
        error_code: str,
        error_message: str,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> LeaseUpdateResult:
        now = datetime.now(UTC)
        dead_letter = attempt_count >= max_attempts
        available_at = now + timedelta(
            seconds=retry_delay_seconds(
                attempt_count,
                base_seconds=retry_base_seconds,
                maximum_seconds=retry_max_seconds,
            )
        )
        result = await self.session.execute(
            update(OutboxEventModel)
            .where(self._lease_condition(event_id, worker_id, lease_version, now))
            .values(
                status=(
                    OutboxStatus.DEAD_LETTER.value
                    if dead_letter
                    else OutboxStatus.FAILED.value
                ),
                available_at=available_at,
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                last_heartbeat_at=None,
                error_code=error_code,
                error_message=error_message,
            )
            .returning(OutboxEventModel.outbox_event_id)
        )
        if result.scalar_one_or_none() is not None:
            return LeaseUpdateResult.UPDATED
        return await self._classify_lease_failure(event_id)

    async def renew_lease(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        lease_version: int,
        lease_seconds: int,
    ) -> LeaseUpdateResult:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(OutboxEventModel)
            .where(self._lease_condition(event_id, worker_id, lease_version, now))
            .values(
                last_heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            .returning(OutboxEventModel.outbox_event_id)
        )
        if result.scalar_one_or_none() is not None:
            return LeaseUpdateResult.UPDATED
        return await self._classify_lease_failure(event_id)

    async def reconcile_stale(
        self,
        *,
        limit: int,
    ) -> Sequence[OutboxEventModel]:
        result = await self.session.execute(
            select(OutboxEventModel)
            .where(
                OutboxEventModel.status == OutboxStatus.PROCESSING.value,
                OutboxEventModel.lease_expires_at <= datetime.now(UTC),
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
            event.lease_expires_at = None
            event.last_heartbeat_at = None
            event.error_code = "OUTBOX_LEASE_EXPIRED"
            event.error_message = "Outbox consumer lease expired"
        await self.session.flush()
        return events

    @staticmethod
    def _lease_condition(
        event_id: UUID, worker_id: str, lease_version: int, now: datetime
    ) -> ColumnElement[bool]:
        return and_(
            OutboxEventModel.outbox_event_id == event_id,
            OutboxEventModel.status == OutboxStatus.PROCESSING.value,
            OutboxEventModel.locked_by == worker_id,
            OutboxEventModel.lease_version == lease_version,
            OutboxEventModel.lease_expires_at > now,
        )

    async def _classify_lease_failure(self, event_id: UUID) -> LeaseUpdateResult:
        result = await self.session.execute(
            select(OutboxEventModel).where(OutboxEventModel.outbox_event_id == event_id)
        )
        event = result.scalar_one_or_none()
        if event is None:
            return LeaseUpdateResult.NOT_FOUND
        if event.status != OutboxStatus.PROCESSING.value:
            return LeaseUpdateResult.INVALID_STATE
        return LeaseUpdateResult.LEASE_LOST

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import time
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.constants import LeaseUpdateResult, OutboxEventType
from app.core.exceptions import ApplicationError
from app.core.sanitization import sanitize_text
from app.database.session import AsyncSessionLocal
from app.observability.context import operation_context
from app.observability.metrics import (
    OUTBOX_DURATION,
    OUTBOX_FAILED,
    OUTBOX_LEASE_LOST,
)
from app.observability.tracing import traced_operation
from app.outbox.consumers import consume_event
from app.outbox.definitions import OutboxEvent
from app.repositories.outbox_repository import OutboxRepository

logger = structlog.get_logger()
Consumer = Callable[[OutboxEvent, AsyncSession], Coroutine[Any, Any, None]]


class OutboxDispatcher:
    def __init__(
        self,
        worker_id: str,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        settings: Settings | None = None,
        consumer: Consumer = consume_event,
    ) -> None:
        self.worker_id = worker_id
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.consumer = consumer

    async def dispatch_once(self, *, limit: int = 50) -> int:
        await self.reconcile_stale(limit=limit)
        dispatched = 0
        for _ in range(min(max(limit, 1), 100)):
            event = await self._lease_one()
            if event is None:
                break
            dispatched += 1
            await self._dispatch_event(event)
        return dispatched

    async def _lease_one(self) -> OutboxEvent | None:
        async with self.session_factory() as session:
            models = await OutboxRepository(session).lease_batch(
                worker_id=self.worker_id,
                limit=1,
                lease_seconds=self.settings.outbox_lease_seconds,
            )
            if not models:
                await session.rollback()
                return None
            model = models[0]
            event = OutboxEvent(
                outbox_event_id=model.outbox_event_id,
                event_type=OutboxEventType(model.event_type),
                aggregate_type=model.aggregate_type,
                aggregate_id=model.aggregate_id,
                payload=model.payload,
                attempt_count=model.attempt_count,
                max_attempts=model.max_attempts,
                lease_version=model.lease_version,
                correlation_id=model.correlation_id,
                trace_id=model.trace_id,
            )
            await session.commit()
            return event

    async def _dispatch_event(self, event: OutboxEvent) -> None:
        started = time.perf_counter()
        lease_lost = asyncio.Event()
        async with self.session_factory() as consumer_session:
            consumer_task: asyncio.Task[None] = asyncio.create_task(
                self.consumer(event, consumer_session)
            )
            heartbeat = asyncio.create_task(
                self._heartbeat_loop(event, consumer_task, lease_lost)
            )
            try:
                with (
                    operation_context(
                        correlation_id=event.correlation_id,
                        trace_id=event.trace_id,
                        outbox_event_id=event.outbox_event_id,
                    ),
                    traced_operation(
                        "outbox.process", event_type=event.event_type.value
                    ),
                ):
                    await consumer_task

                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                if lease_lost.is_set() or not await self._renew_once(event):
                    await consumer_session.rollback()
                    self._record_lease_loss(event, started)
                    return

                result = await OutboxRepository(consumer_session).mark_processed(
                    event.outbox_event_id,
                    worker_id=self.worker_id,
                    lease_version=event.lease_version,
                )
                if result != LeaseUpdateResult.UPDATED:
                    await consumer_session.rollback()
                    self._record_lease_loss(event, started, result=result)
                    return
                await consumer_session.commit()
                logger.info(
                    "outbox_event_processed",
                    outbox_event_id=str(event.outbox_event_id),
                    event_type=event.event_type.value,
                )
                OUTBOX_DURATION.labels(event.event_type.value, "processed").observe(
                    time.perf_counter() - started
                )
            except asyncio.CancelledError:
                await consumer_session.rollback()
                if lease_lost.is_set():
                    self._record_lease_loss(event, started)
                    return
                raise
            except Exception as exc:
                await consumer_session.rollback()
                await self._record_failure(event, exc, started)
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                if not consumer_task.done():
                    consumer_task.cancel()
                    await asyncio.gather(consumer_task, return_exceptions=True)

    async def _heartbeat_loop(
        self,
        event: OutboxEvent,
        consumer_task: asyncio.Task[None],
        lease_lost: asyncio.Event,
    ) -> None:
        while not consumer_task.done():
            await asyncio.sleep(self.settings.outbox_heartbeat_seconds)
            if consumer_task.done():
                return
            if not await self._renew_once(event):
                lease_lost.set()
                consumer_task.cancel()
                return

    async def _renew_once(self, event: OutboxEvent) -> bool:
        try:
            async with self.session_factory() as session:
                result = await OutboxRepository(session).renew_lease(
                    event.outbox_event_id,
                    worker_id=self.worker_id,
                    lease_version=event.lease_version,
                    lease_seconds=self.settings.outbox_lease_seconds,
                )
                if result == LeaseUpdateResult.UPDATED:
                    await session.commit()
                    return True
                await session.rollback()
                return False
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "outbox_heartbeat_failed",
                outbox_event_id=str(event.outbox_event_id),
                worker_id=self.worker_id,
            )
            return False

    async def _record_failure(
        self, event: OutboxEvent, exc: Exception, started: float
    ) -> None:
        async with self.session_factory() as session:
            result = await OutboxRepository(session).mark_failed(
                event.outbox_event_id,
                worker_id=self.worker_id,
                lease_version=event.lease_version,
                attempt_count=event.attempt_count,
                max_attempts=event.max_attempts,
                error_code=(
                    exc.error_code
                    if isinstance(exc, ApplicationError)
                    else "OUTBOX_CONSUMER_ERROR"
                ),
                error_message=(
                    sanitize_text(exc.message, max_characters=2000)
                    if isinstance(exc, ApplicationError)
                    else "Outbox consumer failed"
                ),
                retry_base_seconds=self.settings.outbox_retry_base_seconds,
                retry_max_seconds=self.settings.outbox_retry_max_seconds,
            )
            if result == LeaseUpdateResult.UPDATED:
                await session.commit()
                OUTBOX_FAILED.labels(event.event_type.value).inc()
                OUTBOX_DURATION.labels(event.event_type.value, "failed").observe(
                    time.perf_counter() - started
                )
                return
            await session.rollback()
        self._record_lease_loss(event, started, result=result)

    def _record_lease_loss(
        self,
        event: OutboxEvent,
        started: float,
        *,
        result: LeaseUpdateResult = LeaseUpdateResult.LEASE_LOST,
    ) -> None:
        logger.warning(
            "outbox_lease_lost",
            outbox_event_id=str(event.outbox_event_id),
            worker_id=self.worker_id,
            lease_version=event.lease_version,
            outcome=result.value,
        )
        OUTBOX_LEASE_LOST.labels(event.event_type.value).inc()
        OUTBOX_DURATION.labels(event.event_type.value, "lease_lost").observe(
            time.perf_counter() - started
        )

    async def reconcile_stale(self, *, limit: int = 100) -> int:
        async with self.session_factory() as session:
            events = await OutboxRepository(session).reconcile_stale(
                limit=min(max(limit, 1), 100)
            )
            await session.commit()
        return len(events)

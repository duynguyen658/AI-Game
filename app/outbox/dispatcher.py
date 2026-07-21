from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.constants import OutboxEventType
from app.core.exceptions import ApplicationError
from app.core.sanitization import sanitize_text
from app.database.session import AsyncSessionLocal
from app.outbox.consumers import consume_event
from app.outbox.definitions import OutboxEvent
from app.observability.metrics import OUTBOX_DURATION, OUTBOX_FAILED
from app.observability.context import operation_context
from app.observability.tracing import traced_operation
from app.repositories.outbox_repository import OutboxRepository

logger = structlog.get_logger()
Consumer = Callable[[OutboxEvent, AsyncSession], Awaitable[None]]


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
        async with self.session_factory() as session:
            models = await OutboxRepository(session).lease_batch(
                worker_id=self.worker_id, limit=min(max(limit, 1), 100)
            )
            events = [
                OutboxEvent(
                    outbox_event_id=model.outbox_event_id,
                    event_type=OutboxEventType(model.event_type),
                    aggregate_type=model.aggregate_type,
                    aggregate_id=model.aggregate_id,
                    payload=model.payload,
                    attempt_count=model.attempt_count,
                    max_attempts=model.max_attempts,
                    correlation_id=model.correlation_id,
                    trace_id=model.trace_id,
                )
                for model in models
            ]
            await session.commit()
        for event in events:
            started = time.perf_counter()
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
                    async with self.session_factory() as consumer_session:
                        await self.consumer(event, consumer_session)
                        await consumer_session.commit()
                async with self.session_factory() as session:
                    await OutboxRepository(session).mark_processed(
                        event.outbox_event_id, worker_id=self.worker_id
                    )
                    await session.commit()
                logger.info(
                    "outbox_event_processed",
                    outbox_event_id=str(event.outbox_event_id),
                    event_type=event.event_type.value,
                )
                OUTBOX_DURATION.labels(event.event_type.value, "processed").observe(
                    time.perf_counter() - started
                )
            except Exception as exc:
                async with self.session_factory() as session:
                    await OutboxRepository(session).mark_failed(
                        event.outbox_event_id,
                        worker_id=self.worker_id,
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
                        retry_base_seconds=self.settings.job_retry_base_seconds,
                        retry_max_seconds=self.settings.job_retry_max_seconds,
                    )
                    await session.commit()
                OUTBOX_FAILED.labels(event.event_type.value).inc()
                OUTBOX_DURATION.labels(event.event_type.value, "failed").observe(
                    time.perf_counter() - started
                )
        return len(events)

    async def reconcile_stale(self, *, limit: int = 100) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.job_lease_seconds)
        async with self.session_factory() as session:
            events = await OutboxRepository(session).reconcile_stale(
                older_than=cutoff, limit=min(max(limit, 1), 100)
            )
            await session.commit()
        return len(events)

from __future__ import annotations

import hashlib

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import JobType, OutboxEventType
from app.jobs.definitions import (
    AlertReconciliationJobPayload,
    EvaluationRunJobPayload,
    JobPayload,
    MemoryReconciliationJobPayload,
)
from app.jobs.queue import JobQueue
from app.outbox.definitions import OutboxEvent

logger = structlog.get_logger()


async def consume_event(event: OutboxEvent, session: AsyncSession) -> None:
    if event.event_type == OutboxEventType.MEMORY_RECONCILIATION_REQUIRED:
        await _enqueue_from_event(
            event,
            session,
            JobType.MEMORY_RECONCILIATION,
            MemoryReconciliationJobPayload(limit=100),
        )
    elif event.event_type in {
        OutboxEventType.WORKFLOW_FAILED,
        OutboxEventType.ACTION_FAILED,
    }:
        await _enqueue_from_event(
            event,
            session,
            JobType.ALERT_RECONCILIATION,
            AlertReconciliationJobPayload(limit=100),
        )
    elif event.event_type == OutboxEventType.EVALUATION_REQUESTED:
        await _enqueue_from_event(
            event,
            session,
            JobType.EVALUATION_RUN,
            EvaluationRunJobPayload(
                evaluation_run_id=event.payload["evaluation_run_id"]
            ),
        )
    else:
        logger.info(
            "outbox_audit_event_consumed",
            outbox_event_id=str(event.outbox_event_id),
            event_type=event.event_type.value,
        )


async def _enqueue_from_event(
    event: OutboxEvent,
    session: AsyncSession,
    job_type: JobType,
    payload: JobPayload,
) -> None:
    key = hashlib.sha256(
        f"outbox|{event.outbox_event_id}|{job_type.value}".encode()
    ).hexdigest()
    await JobQueue(session).enqueue(
        job_type,
        payload,
        created_by="outbox-consumer",
        idempotency_key=key,
        correlation_id=event.correlation_id,
        trace_id=event.trace_id,
    )

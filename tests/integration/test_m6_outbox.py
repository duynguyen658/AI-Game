from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import OutboxEventType, OutboxStatus
from app.database.models import OutboxEventModel
from app.database.session import AsyncSessionLocal
from app.outbox.definitions import OutboxEvent
from app.outbox.dispatcher import OutboxDispatcher
from app.outbox.service import OutboxService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_outbox_database() -> AsyncIterator[None]:
    statement = text("TRUNCATE outbox_events RESTART IDENTITY CASCADE")
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_outbox_is_transactional_and_idempotent(
    db_session: AsyncSession,
) -> None:
    service = OutboxService(db_session)
    event = await service.add_event(
        event_type=OutboxEventType.WORKFLOW_COMPLETED,
        aggregate_type="workflow",
        aggregate_id="workflow-1",
        payload={"status": "PENDING_APPROVAL"},
        idempotency_key="workflow-1-completed",
    )
    duplicate = await service.add_event(
        event_type=OutboxEventType.WORKFLOW_COMPLETED,
        aggregate_type="workflow",
        aggregate_id="workflow-1",
        payload={"status": "PENDING_APPROVAL"},
        idempotency_key="workflow-1-completed",
    )
    assert duplicate.outbox_event_id == event.outbox_event_id
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count(OutboxEventModel.outbox_event_id))
    )
    assert count == 1

    await service.add_event(
        event_type=OutboxEventType.WORKFLOW_FAILED,
        aggregate_type="workflow",
        aggregate_id="workflow-2",
        payload={"error_code": "TEST"},
        idempotency_key="workflow-2-failed",
    )
    await db_session.rollback()
    rolled_back = await db_session.scalar(
        select(func.count(OutboxEventModel.outbox_event_id)).where(
            OutboxEventModel.idempotency_key == "workflow-2-failed"
        )
    )
    assert rolled_back == 0


@pytest.mark.asyncio
async def test_outbox_failure_is_retained_and_retried_once() -> None:
    async with AsyncSessionLocal() as session:
        await OutboxService(session).add_event(
            event_type=OutboxEventType.WORKFLOW_COMPLETED,
            aggregate_type="workflow",
            aggregate_id="workflow-1",
            payload={"status": "PENDING_APPROVAL"},
            idempotency_key="dispatch-once",
        )
        await session.commit()

    calls = 0

    async def flaky_consumer(_: OutboxEvent, __: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected consumer failure")

    settings = get_settings().model_copy(
        update={"job_retry_base_seconds": 1, "job_retry_max_seconds": 1}
    )
    dispatcher = OutboxDispatcher(
        "outbox-test-worker", settings=settings, consumer=flaky_consumer
    )
    assert await dispatcher.dispatch_once() == 1

    async with AsyncSessionLocal() as session:
        failed = (await session.execute(select(OutboxEventModel))).scalar_one()
        assert failed.status == OutboxStatus.FAILED.value
        assert failed.attempt_count == 1
        await session.execute(
            update(OutboxEventModel).values(available_at=datetime.now(UTC))
        )
        await session.commit()

    assert await dispatcher.dispatch_once() == 1
    assert await dispatcher.dispatch_once() == 0
    assert calls == 2
    async with AsyncSessionLocal() as session:
        processed = (await session.execute(select(OutboxEventModel))).scalar_one()
        assert processed.status == OutboxStatus.PROCESSED.value
        assert processed.attempt_count == 2

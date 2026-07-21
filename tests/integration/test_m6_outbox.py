from __future__ import annotations

import os
import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import (
    JobStatus,
    JobType,
    LeaseUpdateResult,
    OutboxEventType,
    OutboxStatus,
)
from app.database.models import BackgroundJobModel, OutboxEventModel
from app.database.session import AsyncSessionLocal
from app.jobs.definitions import LeasedJob, MemoryReconciliationJobPayload
from app.jobs.queue import JobQueue
from app.jobs.worker import JobControl, JobWorker
from app.outbox.consumers import consume_event
from app.outbox.definitions import OutboxEvent
from app.outbox.dispatcher import OutboxDispatcher
from app.outbox.service import OutboxService
from app.repositories.outbox_repository import OutboxRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_outbox_database() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE outbox_events, job_attempts, background_jobs, worker_heartbeats "
        "RESTART IDENTITY CASCADE"
    )
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


@pytest.mark.asyncio
async def test_stale_owner_is_fenced_after_event_is_released() -> None:
    async with AsyncSessionLocal() as session:
        await OutboxService(session).add_event(
            event_type=OutboxEventType.WORKFLOW_COMPLETED,
            aggregate_type="workflow",
            aggregate_id="workflow-fenced",
            payload={"status": "PENDING_APPROVAL"},
            idempotency_key="fenced-owner",
        )
        await session.commit()

        old = (
            await OutboxRepository(session).lease_batch(
                worker_id="old-worker", limit=1, lease_seconds=5
            )
        )[0]
        event_id = old.outbox_event_id
        old_version = old.lease_version
        await session.commit()

        await session.execute(
            update(OutboxEventModel)
            .where(OutboxEventModel.outbox_event_id == event_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
        assert len(await OutboxRepository(session).reconcile_stale(limit=1)) == 1
        await session.commit()

        current = (
            await OutboxRepository(session).lease_batch(
                worker_id="new-worker", limit=1, lease_seconds=30
            )
        )[0]
        await session.commit()
        current_version = current.lease_version
        assert current_version == old_version + 1

        stale_result = await OutboxRepository(session).mark_processed(
            event_id, worker_id="old-worker", lease_version=old_version
        )
        assert stale_result == LeaseUpdateResult.LEASE_LOST
        await session.rollback()

        current_result = await OutboxRepository(session).mark_processed(
            event_id,
            worker_id="new-worker",
            lease_version=current_version,
        )
        assert current_result == LeaseUpdateResult.UPDATED
        await session.commit()


@pytest.mark.asyncio
async def test_consumer_side_effect_is_rolled_back_when_lease_is_lost() -> None:
    async with AsyncSessionLocal() as session:
        primary = await OutboxService(session).add_event(
            event_type=OutboxEventType.WORKFLOW_COMPLETED,
            aggregate_type="workflow",
            aggregate_id="workflow-race",
            payload={"status": "PENDING_APPROVAL"},
            idempotency_key="lease-race-primary",
        )
        primary_id = primary.outbox_event_id
        await session.commit()

    side_effect_ready = asyncio.Event()
    release_consumer = asyncio.Event()

    async def delayed_consumer(_: OutboxEvent, session: AsyncSession) -> None:
        await OutboxService(session).add_event(
            event_type=OutboxEventType.WORKFLOW_COMPLETED,
            aggregate_type="workflow",
            aggregate_id="uncommitted-side-effect",
            payload={"status": "PENDING_APPROVAL"},
            idempotency_key="lease-race-side-effect",
        )
        side_effect_ready.set()
        await release_consumer.wait()

    dispatcher = OutboxDispatcher("stale-worker", consumer=delayed_consumer)
    dispatch_task = asyncio.create_task(dispatcher.dispatch_once(limit=1))
    await asyncio.wait_for(side_effect_ready.wait(), timeout=5)

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(OutboxEventModel)
            .where(OutboxEventModel.outbox_event_id == primary_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    replacement = OutboxDispatcher(
        "replacement-worker", consumer=lambda _event, _session: asyncio.sleep(0)
    )
    assert await replacement.dispatch_once(limit=1) == 1
    release_consumer.set()
    assert await asyncio.wait_for(dispatch_task, timeout=5) == 1

    async with AsyncSessionLocal() as session:
        side_effect_count = await session.scalar(
            select(func.count(OutboxEventModel.outbox_event_id)).where(
                OutboxEventModel.idempotency_key == "lease-race-side-effect"
            )
        )
        assert side_effect_count == 0
        primary_status = await session.scalar(
            select(OutboxEventModel.status).where(
                OutboxEventModel.outbox_event_id == primary_id
            )
        )
        assert primary_status == OutboxStatus.PROCESSED.value


@pytest.mark.asyncio
async def test_worker_continues_when_outbox_dispatcher_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as session:
        await JobQueue(session).enqueue(
            JobType.MEMORY_RECONCILIATION,
            MemoryReconciliationJobPayload(limit=1),
            created_by="worker-isolation-test",
            idempotency_key="worker-isolation-job",
        )

    handled = asyncio.Event()

    async def handler(_: LeasedJob, __: JobControl) -> None:
        handled.set()

    async def fail_dispatcher(_: OutboxDispatcher, *, limit: int = 50) -> int:
        raise RuntimeError(f"injected dispatcher failure at limit {limit}")

    monkeypatch.setattr(OutboxDispatcher, "dispatch_once", fail_dispatcher)
    worker = JobWorker(
        "isolated-worker",
        {JobType.MEMORY_RECONCILIATION: handler},
    )
    assert await worker.run_once() == 1
    assert handled.is_set()

    async with AsyncSessionLocal() as session:
        status = await session.scalar(select(BackgroundJobModel.status))
        assert status == JobStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_long_running_consumer_renews_its_lease() -> None:
    async with AsyncSessionLocal() as session:
        event = await OutboxService(session).add_event(
            event_type=OutboxEventType.WORKFLOW_COMPLETED,
            aggregate_type="workflow",
            aggregate_id="workflow-heartbeat",
            payload={"status": "PENDING_APPROVAL"},
            idempotency_key="heartbeat-primary",
        )
        event_id = event.outbox_event_id
        await session.commit()

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_consumer(_: OutboxEvent, __: AsyncSession) -> None:
        started.set()
        await release.wait()

    settings = get_settings().model_copy(
        update={"outbox_lease_seconds": 5, "outbox_heartbeat_seconds": 1}
    )
    dispatcher = OutboxDispatcher(
        "heartbeat-worker", settings=settings, consumer=slow_consumer
    )
    task = asyncio.create_task(dispatcher.dispatch_once(limit=1))
    await asyncio.wait_for(started.wait(), timeout=5)
    async with AsyncSessionLocal() as session:
        initial_expiry = await session.scalar(
            select(OutboxEventModel.lease_expires_at).where(
                OutboxEventModel.outbox_event_id == event_id
            )
        )

    renewed_expiry = initial_expiry
    async with asyncio.timeout(3):
        while renewed_expiry == initial_expiry:
            await asyncio.sleep(0.05)
            async with AsyncSessionLocal() as session:
                renewed_expiry = await session.scalar(
                    select(OutboxEventModel.lease_expires_at).where(
                        OutboxEventModel.outbox_event_id == event_id
                    )
                )
    assert initial_expiry is not None
    assert renewed_expiry is not None
    assert renewed_expiry > initial_expiry
    assert await OutboxDispatcher("reclaimer").reconcile_stale(limit=1) == 0

    release.set()
    assert await asyncio.wait_for(task, timeout=5) == 1


@pytest.mark.asyncio
async def test_two_dispatchers_process_each_event_once() -> None:
    async with AsyncSessionLocal() as session:
        for index in range(10):
            await OutboxService(session).add_event(
                event_type=OutboxEventType.WORKFLOW_COMPLETED,
                aggregate_type="workflow",
                aggregate_id=f"workflow-race-{index}",
                payload={"index": index},
                idempotency_key=f"two-dispatchers-{index}",
            )
        await session.commit()

    consumed: list[str] = []

    async def record_consumer(event: OutboxEvent, _: AsyncSession) -> None:
        consumed.append(str(event.outbox_event_id))
        await asyncio.sleep(0)

    first = OutboxDispatcher("dispatcher-a", consumer=record_consumer)
    second = OutboxDispatcher("dispatcher-b", consumer=record_consumer)
    counts = await asyncio.gather(
        first.dispatch_once(limit=10), second.dispatch_once(limit=10)
    )
    assert sum(counts) == 10
    assert len(consumed) == 10
    assert len(set(consumed)) == 10
    async with AsyncSessionLocal() as session:
        processed = await session.scalar(
            select(func.count(OutboxEventModel.outbox_event_id)).where(
                OutboxEventModel.status == OutboxStatus.PROCESSED.value
            )
        )
        assert processed == 10


@pytest.mark.asyncio
async def test_default_consumer_does_not_commit_job_side_effect_early() -> None:
    event = OutboxEvent(
        outbox_event_id=uuid4(),
        event_type=OutboxEventType.EVALUATION_REQUESTED,
        aggregate_type="evaluation_run",
        aggregate_id=str(uuid4()),
        payload={"evaluation_run_id": str(uuid4())},
        attempt_count=1,
        max_attempts=5,
        lease_version=1,
        correlation_id=str(uuid4()),
    )
    async with AsyncSessionLocal() as consumer_session:
        await consume_event(event, consumer_session)
        async with AsyncSessionLocal() as observer_session:
            visible_before_commit = await observer_session.scalar(
                select(func.count(BackgroundJobModel.job_id))
            )
            assert visible_before_commit == 0
        await consumer_session.rollback()

    async with AsyncSessionLocal() as session:
        visible_after_rollback = await session.scalar(
            select(func.count(BackgroundJobModel.job_id))
        )
        assert visible_after_rollback == 0

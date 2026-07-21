from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import JobStatus, JobType
from app.core.exceptions import JobLeaseLostError
from app.database.models import BackgroundJobModel, JobAttemptModel
from app.database.session import AsyncSessionLocal
from app.jobs.definitions import MemoryReconciliationJobPayload
from app.jobs.queue import JobQueue

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_job_database() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE job_attempts, background_jobs, worker_heartbeats "
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
async def test_enqueue_is_idempotent_and_payload_is_typed(
    db_session: AsyncSession,
) -> None:
    queue = JobQueue(db_session)
    payload = MemoryReconciliationJobPayload(limit=20)
    first = await queue.enqueue(
        JobType.MEMORY_RECONCILIATION,
        payload,
        created_by="test-suite",
    )
    second = await queue.enqueue(
        JobType.MEMORY_RECONCILIATION,
        payload,
        created_by="test-suite",
    )

    assert first.job_id == second.job_id
    assert first.status == JobStatus.PENDING
    rows = (await db_session.execute(select(BackgroundJobModel))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_two_workers_lease_distinct_jobs() -> None:
    async with AsyncSessionLocal() as session:
        queue = JobQueue(session)
        for limit in (11, 12):
            await queue.enqueue(
                JobType.MEMORY_RECONCILIATION,
                MemoryReconciliationJobPayload(limit=limit),
                created_by="test-suite",
            )
    barrier = asyncio.Barrier(2)

    async def lease(worker_id: str):
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            return await JobQueue(session).lease(worker_id=worker_id, limit=1)

    first, second = await asyncio.gather(lease("worker-a"), lease("worker-b"))
    assert len(first) == len(second) == 1
    assert first[0].job_id != second[0].job_id


@pytest.mark.asyncio
async def test_retry_dead_letter_and_stale_worker_fencing(
    db_session: AsyncSession,
) -> None:
    settings = get_settings().model_copy(
        update={
            "job_max_attempts": 2,
            "job_retry_base_seconds": 1,
            "job_retry_max_seconds": 1,
        }
    )
    queue = JobQueue(db_session, settings=settings)
    job = await queue.enqueue(
        JobType.MEMORY_RECONCILIATION,
        MemoryReconciliationJobPayload(limit=10),
        created_by="test-suite",
        max_attempts=2,
    )
    leased = (await queue.lease(worker_id="worker-old", limit=1))[0]
    failed = await queue.fail(
        leased.job_id,
        worker_id="worker-old",
        error_code="TEMPORARY",
        error_message="retry later",
        retryable=True,
    )
    assert failed.status == JobStatus.PENDING

    model = await db_session.get(BackgroundJobModel, job.job_id)
    assert model is not None
    model.available_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    second = (await queue.lease(worker_id="worker-old", limit=1))[0]
    dead = await queue.fail(
        second.job_id,
        worker_id="worker-old",
        error_code="STILL_FAILING",
        error_message="no attempts remain",
        retryable=True,
    )
    assert dead.status == JobStatus.DEAD_LETTER

    retried = await queue.retry(job.job_id)
    assert retried.status == JobStatus.PENDING
    reclaimed_lease = (await queue.lease(worker_id="worker-stale", limit=1))[0]
    running = await db_session.get(BackgroundJobModel, reclaimed_lease.job_id)
    assert running is not None
    running.max_attempts = 4
    running.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    reclaimed = await queue.reclaim_stale(limit=1)
    assert reclaimed[0].status == JobStatus.PENDING
    with pytest.raises(JobLeaseLostError):
        await queue.complete(reclaimed_lease.job_id, worker_id="worker-stale")

    attempts = (
        (
            await db_session.execute(
                select(JobAttemptModel).where(JobAttemptModel.job_id == job.job_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_unknown_job_type_is_dead_lettered_without_crashing(
    db_session: AsyncSession,
) -> None:
    model = BackgroundJobModel(
        job_type="UNKNOWN_TYPE",
        status=JobStatus.PENDING.value,
        payload={},
        priority=50,
        max_attempts=5,
        available_at=datetime.now(UTC),
        idempotency_key="unknown-job-type",
        correlation_id="6a6e1b0d-596f-49e8-8381-72fb1e036adb",
        created_by="test-suite",
    )
    db_session.add(model)
    await db_session.commit()

    assert await JobQueue(db_session).lease(worker_id="safe-worker", limit=1) == []
    await db_session.refresh(model)
    assert model.status == JobStatus.DEAD_LETTER.value
    assert model.error_code == "UNKNOWN_JOB_TYPE"

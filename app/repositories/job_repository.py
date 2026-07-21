from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    JobAttemptStatus,
    JobStatus,
    JobType,
    WorkerStatus,
)
from app.core.exceptions import JobConflictError, JobLeaseLostError
from app.database.models import (
    BackgroundJobModel,
    JobAttemptModel,
    WorkerHeartbeatModel,
)
from app.jobs.retry import retry_delay_seconds


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        job_type: JobType,
        payload: dict[str, object],
        priority: int,
        max_attempts: int,
        available_at: datetime,
        idempotency_key: str,
        correlation_id: str,
        trace_id: str | None,
        created_by: str,
    ) -> BackgroundJobModel:
        model = BackgroundJobModel(
            job_type=job_type.value,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            available_at=available_at,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            trace_id=trace_id,
            created_by=created_by,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(
        self, job_id: UUID, *, with_attempts: bool = False
    ) -> BackgroundJobModel | None:
        statement = select(BackgroundJobModel).where(
            BackgroundJobModel.job_id == job_id
        )
        if with_attempts:
            statement = statement.options(selectinload(BackgroundJobModel.attempts))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self, idempotency_key: str
    ) -> BackgroundJobModel | None:
        result = await self.session.execute(
            select(BackgroundJobModel).where(
                BackgroundJobModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
    ) -> Sequence[BackgroundJobModel]:
        statement: Select[tuple[BackgroundJobModel]] = select(BackgroundJobModel)
        if status is not None:
            statement = statement.where(BackgroundJobModel.status == status.value)
        if job_type is not None:
            statement = statement.where(BackgroundJobModel.job_type == job_type.value)
        result = await self.session.execute(
            statement.order_by(
                BackgroundJobModel.created_at.desc(), BackgroundJobModel.job_id
            )
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def lease_batch(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> Sequence[BackgroundJobModel]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(BackgroundJobModel)
            .where(
                BackgroundJobModel.status == JobStatus.PENDING.value,
                BackgroundJobModel.available_at <= now,
                BackgroundJobModel.cancel_requested.is_(False),
            )
            .order_by(
                BackgroundJobModel.priority.desc(),
                BackgroundJobModel.available_at,
                BackgroundJobModel.created_at,
                BackgroundJobModel.job_id,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = result.scalars().all()
        for job in jobs:
            job.status = JobStatus.RUNNING.value
            job.locked_by = worker_id
            job.locked_at = now
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.started_at = job.started_at or now
            job.attempt_count += 1
            job.error_code = None
            job.error_message = None
            self.session.add(
                JobAttemptModel(
                    job_id=job.job_id,
                    attempt_number=job.attempt_count,
                    worker_id=worker_id,
                    status=JobAttemptStatus.RUNNING.value,
                    started_at=now,
                )
            )
        await self.session.flush()
        return jobs

    async def heartbeat(
        self, job_id: UUID, *, worker_id: str, lease_seconds: int
    ) -> bool:
        now = datetime.now(UTC)
        job = await self._get_for_update(job_id)
        if job is None or not self._owns_live_lease(job, worker_id, now):
            return False
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        await self.session.flush()
        return True

    async def complete(self, job_id: UUID, *, worker_id: str) -> BackgroundJobModel:
        now = datetime.now(UTC)
        job = await self._required_live_lease(job_id, worker_id, now)
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = now
        self._clear_lease(job)
        await self._finish_attempt(
            job, worker_id=worker_id, status=JobAttemptStatus.SUCCEEDED, now=now
        )
        await self.session.flush()
        return job

    async def fail(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        error_code: str,
        error_message: str,
        retryable: bool,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> BackgroundJobModel:
        now = datetime.now(UTC)
        job = await self._required_live_lease(job_id, worker_id, now)
        await self._finish_attempt(
            job,
            worker_id=worker_id,
            status=JobAttemptStatus.FAILED,
            now=now,
            error_code=error_code,
            error_message=error_message,
        )
        job.error_code = error_code
        job.error_message = error_message
        if retryable and job.attempt_count < job.max_attempts:
            job.status = JobStatus.PENDING.value
            job.available_at = now + timedelta(
                seconds=retry_delay_seconds(
                    job.attempt_count,
                    base_seconds=retry_base_seconds,
                    maximum_seconds=retry_max_seconds,
                )
            )
        else:
            job.status = JobStatus.DEAD_LETTER.value
            job.completed_at = now
        self._clear_lease(job)
        await self.session.flush()
        return job

    async def cancel(self, job_id: UUID) -> BackgroundJobModel:
        job = await self._get_for_update(job_id)
        if job is None:
            raise JobConflictError("Job is unavailable")
        status = JobStatus(job.status)
        if status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED.value
            job.cancel_requested = True
            job.completed_at = datetime.now(UTC)
        elif status == JobStatus.RUNNING:
            job.cancel_requested = True
        elif status not in {JobStatus.CANCELLED, JobStatus.SUCCEEDED}:
            raise JobConflictError("Job cannot be cancelled in its current state")
        await self.session.flush()
        return job

    async def mark_cancelled(
        self, job_id: UUID, *, worker_id: str
    ) -> BackgroundJobModel:
        now = datetime.now(UTC)
        job = await self._required_live_lease(job_id, worker_id, now)
        job.status = JobStatus.CANCELLED.value
        job.cancel_requested = True
        job.completed_at = now
        self._clear_lease(job)
        await self._finish_attempt(
            job, worker_id=worker_id, status=JobAttemptStatus.CANCELLED, now=now
        )
        await self.session.flush()
        return job

    async def retry(self, job_id: UUID) -> BackgroundJobModel:
        job = await self._get_for_update(job_id)
        if job is None:
            raise JobConflictError("Job is unavailable")
        if JobStatus(job.status) not in {
            JobStatus.FAILED,
            JobStatus.DEAD_LETTER,
            JobStatus.CANCELLED,
        }:
            raise JobConflictError("Job is not retryable in its current state")
        job.status = JobStatus.PENDING.value
        job.cancel_requested = False
        job.available_at = datetime.now(UTC)
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        if job.attempt_count >= job.max_attempts:
            job.max_attempts = job.attempt_count + 1
        self._clear_lease(job)
        await self.session.flush()
        return job

    async def reclaim_stale(
        self,
        *,
        limit: int,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> Sequence[BackgroundJobModel]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(BackgroundJobModel)
            .where(
                BackgroundJobModel.status == JobStatus.RUNNING.value,
                BackgroundJobModel.lease_expires_at <= now,
            )
            .order_by(BackgroundJobModel.lease_expires_at, BackgroundJobModel.job_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = result.scalars().all()
        for job in jobs:
            await self._finish_attempt(
                job,
                worker_id=job.locked_by or "expired-worker",
                status=JobAttemptStatus.FAILED,
                now=now,
                error_code="JOB_LEASE_EXPIRED",
                error_message="Worker lease expired before completion",
            )
            job.error_code = "JOB_LEASE_EXPIRED"
            job.error_message = "Worker lease expired before completion"
            if job.attempt_count < job.max_attempts:
                job.status = JobStatus.PENDING.value
                job.available_at = now + timedelta(
                    seconds=retry_delay_seconds(
                        job.attempt_count,
                        base_seconds=retry_base_seconds,
                        maximum_seconds=retry_max_seconds,
                    )
                )
            else:
                job.status = JobStatus.DEAD_LETTER.value
                job.completed_at = now
            self._clear_lease(job)
        await self.session.flush()
        return jobs

    async def cancellation_requested(self, job_id: UUID, *, worker_id: str) -> bool:
        result = await self.session.execute(
            select(BackgroundJobModel.cancel_requested).where(
                BackgroundJobModel.job_id == job_id,
                BackgroundJobModel.status == JobStatus.RUNNING.value,
                BackgroundJobModel.locked_by == worker_id,
            )
        )
        return bool(result.scalar_one_or_none())

    async def update_worker_heartbeat(
        self,
        *,
        worker_id: str,
        status: WorkerStatus,
        current_job_id: UUID | None,
        increment_processed: bool = False,
    ) -> WorkerHeartbeatModel:
        now = datetime.now(UTC)
        statement = insert(WorkerHeartbeatModel).values(
            worker_id=worker_id,
            status=status.value,
            started_at=now,
            last_seen_at=now,
            current_job_id=current_job_id,
            processed_count=1 if increment_processed else 0,
        )
        model = (
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[WorkerHeartbeatModel.worker_id],
                    set_={
                        "status": status.value,
                        "last_seen_at": now,
                        "current_job_id": current_job_id,
                        "processed_count": (
                            WorkerHeartbeatModel.processed_count + 1
                            if increment_processed
                            else WorkerHeartbeatModel.processed_count
                        ),
                    },
                ).returning(WorkerHeartbeatModel)
            )
        ).scalar_one()
        await self.session.flush()
        return model

    async def _get_for_update(self, job_id: UUID) -> BackgroundJobModel | None:
        result = await self.session.execute(
            select(BackgroundJobModel)
            .where(BackgroundJobModel.job_id == job_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _required_live_lease(
        self, job_id: UUID, worker_id: str, now: datetime
    ) -> BackgroundJobModel:
        job = await self._get_for_update(job_id)
        if job is None or not self._owns_live_lease(job, worker_id, now):
            raise JobLeaseLostError("Job lease is no longer owned by this worker")
        return job

    @staticmethod
    def _owns_live_lease(
        job: BackgroundJobModel | None, worker_id: str, now: datetime
    ) -> bool:
        return bool(
            job is not None
            and job.status == JobStatus.RUNNING.value
            and job.locked_by == worker_id
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )

    async def _finish_attempt(
        self,
        job: BackgroundJobModel,
        *,
        worker_id: str,
        status: JobAttemptStatus,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        result = await self.session.execute(
            select(JobAttemptModel)
            .where(
                JobAttemptModel.job_id == job.job_id,
                JobAttemptModel.attempt_number == job.attempt_count,
                JobAttemptModel.status == JobAttemptStatus.RUNNING.value,
            )
            .with_for_update()
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise JobConflictError("Active job attempt audit is missing")
        attempt.worker_id = worker_id
        attempt.status = status.value
        attempt.completed_at = now
        attempt.duration_ms = max(
            int((now - attempt.started_at).total_seconds() * 1000), 0
        )
        attempt.error_code = error_code
        attempt.error_message = error_message

    @staticmethod
    def _clear_lease(job: BackgroundJobModel) -> None:
        job.locked_by = None
        job.locked_at = None
        job.lease_expires_at = None
        job.heartbeat_at = None

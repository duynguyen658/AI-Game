from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ApplicationError,
    JobCancelledError,
    JobLeaseLostError,
    JobPayloadError,
    MediaAttemptLeaseLostError,
)
from app.database.session import AsyncSessionLocal
from app.jobs.definitions import LeasedJob
from app.jobs.queue import JobQueue
from app.jobs.lifecycle import JobTerminalReconciler
from app.jobs.retry import classify_job_error
from app.observability.context import operation_context
from app.observability.metrics import JOB_DURATION, OUTBOX_DISPATCHER_ERRORS
from app.observability.tracing import traced_operation
from app.outbox.dispatcher import OutboxDispatcher
from app.repositories.job_repository import JobRepository
from app.core.constants import JobErrorClassification, JobStatus, JobType, WorkerStatus

logger = structlog.get_logger()


@dataclass
class JobControl:
    job_id: UUID
    worker_id: str
    session_factory: async_sessionmaker[AsyncSession]

    async def checkpoint(self) -> None:
        async with self.session_factory() as session:
            requested = await JobQueue(session).cancellation_requested(
                self.job_id, worker_id=self.worker_id
            )
        if requested:
            raise JobCancelledError("Job cancellation was requested")


JobHandler = Callable[[LeasedJob, JobControl], Coroutine[Any, Any, None]]


class JobWorker:
    def __init__(
        self,
        worker_id: str,
        handlers: Mapping[JobType, JobHandler],
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        settings: Settings | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.handlers = dict(handlers)
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.stop_event = asyncio.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    async def run_forever(self) -> None:
        await self._worker_heartbeat(WorkerStatus.STARTING)
        await self._worker_heartbeat(WorkerStatus.RUNNING)
        try:
            while not self.stop_event.is_set():
                try:
                    processed = await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "worker_iteration_failed", worker_id=self.worker_id
                    )
                    processed = 0
                if not processed:
                    try:
                        await asyncio.wait_for(
                            self.stop_event.wait(),
                            timeout=self.settings.job_poll_interval_seconds,
                        )
                    except TimeoutError:
                        pass
        finally:
            await self._worker_heartbeat(WorkerStatus.STOPPED)

    async def run_once(self) -> int:
        try:
            await OutboxDispatcher(
                f"{self.worker_id}:outbox",
                session_factory=self.session_factory,
                settings=self.settings,
            ).dispatch_once(limit=self.settings.outbox_batch_size)
        except asyncio.CancelledError:
            raise
        except Exception:
            OUTBOX_DISPATCHER_ERRORS.inc()
            logger.exception(
                "outbox_dispatch_iteration_failed", worker_id=self.worker_id
            )
        async with self.session_factory() as session:
            queue = JobQueue(session, settings=self.settings)
            await queue.reclaim_stale()
            leased = await queue.lease(worker_id=self.worker_id)
        if not leased:
            await self._worker_heartbeat(WorkerStatus.RUNNING)
            return 0
        await asyncio.gather(*(self._process(job) for job in leased))
        return len(leased)

    async def _process(self, job: LeasedJob) -> None:
        started = time.perf_counter()
        outcome = "failed"
        handler = self.handlers.get(job.job_type)
        control = JobControl(job.job_id, self.worker_id, self.session_factory)
        lease_lost = asyncio.Event()
        cancellation = asyncio.Event()
        with operation_context(
            correlation_id=job.correlation_id,
            trace_id=job.trace_id,
            job_id=job.job_id,
        ):
            with traced_operation(
                "job.execute", job_type=job.job_type.value, attempt=job.attempt_count
            ):
                await self._worker_heartbeat(
                    WorkerStatus.RUNNING, current_job_id=job.job_id
                )
                if handler is None:
                    await self._fail(
                        job,
                        JobPayloadError("No handler is registered for this job type"),
                        retryable=False,
                    )
                    return
                task: asyncio.Task[None] = asyncio.create_task(handler(job, control))
                heartbeat = asyncio.create_task(
                    self._heartbeat_loop(job.job_id, task, lease_lost, cancellation)
                )
                try:
                    await task
                    if lease_lost.is_set():
                        raise JobLeaseLostError("Job lease was lost during execution")
                    async with self.session_factory() as session:
                        media_success = await JobTerminalReconciler(
                            session
                        ).ensure_success_consistency(job)
                    if not media_success:
                        await control.checkpoint()
                    async with self.session_factory() as session:
                        await JobQueue(session, settings=self.settings).complete(
                            job.job_id, worker_id=self.worker_id
                        )
                    outcome = "succeeded"
                except JobCancelledError:
                    await self._cancel(job)
                    outcome = "cancelled"
                except asyncio.CancelledError:
                    if cancellation.is_set():
                        await self._cancel(job)
                        outcome = "cancelled"
                    elif lease_lost.is_set():
                        logger.warning(
                            "job_lease_lost",
                            job_id=str(job.job_id),
                            worker_id=self.worker_id,
                        )
                        outcome = "lease_lost"
                    else:
                        raise
                except MediaAttemptLeaseLostError:
                    logger.warning(
                        "media_attempt_ownership_lost",
                        job_id=str(job.job_id),
                        worker_id=self.worker_id,
                    )
                    outcome = "lease_lost"
                except Exception as exc:
                    if not lease_lost.is_set():
                        await self._fail(job, exc, retryable=self._is_retryable(exc))
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                    await self._worker_heartbeat(
                        WorkerStatus.RUNNING, increment_processed=True
                    )
                    JOB_DURATION.labels(job.job_type.value, outcome).observe(
                        time.perf_counter() - started
                    )

    async def _heartbeat_loop(
        self,
        job_id: UUID,
        handler_task: asyncio.Task[None],
        lease_lost: asyncio.Event,
        cancellation: asyncio.Event,
    ) -> None:
        while not handler_task.done():
            await asyncio.sleep(self.settings.job_heartbeat_seconds)
            if handler_task.done():
                return
            async with self.session_factory() as session:
                queue = JobQueue(session, settings=self.settings)
                if await queue.cancellation_requested(job_id, worker_id=self.worker_id):
                    cancellation.set()
                    handler_task.cancel()
                    return
                if not await queue.heartbeat(job_id, worker_id=self.worker_id):
                    lease_lost.set()
                    handler_task.cancel()
                    return

    async def _fail(self, job: LeasedJob, error: Exception, *, retryable: bool) -> None:
        code = (
            error.error_code
            if isinstance(error, ApplicationError)
            else "JOB_HANDLER_ERROR"
        )
        message = (
            error.message
            if isinstance(error, ApplicationError)
            else "Background job handler failed"
        )
        async with self.session_factory() as session:
            result = await JobQueue(session, settings=self.settings).fail(
                job.job_id,
                worker_id=self.worker_id,
                error_code=code,
                error_message=message,
                retryable=retryable,
            )
            if result.status == JobStatus.DEAD_LETTER:
                await JobTerminalReconciler(session).reconcile(
                    job,
                    cancelled=False,
                    error_code=code,
                    error_message=message,
                )

    async def _cancel(self, job: LeasedJob) -> None:
        async with self.session_factory() as session:
            await JobQueue(session, settings=self.settings).mark_cancelled(
                job.job_id, worker_id=self.worker_id
            )
            await JobTerminalReconciler(session).reconcile(
                job,
                cancelled=True,
                error_code="JOB_CANCELLED",
                error_message="Background job was cancelled",
            )

    async def _worker_heartbeat(
        self,
        status: WorkerStatus,
        *,
        current_job_id: UUID | None = None,
        increment_processed: bool = False,
    ) -> None:
        async with self.session_factory() as session:
            await JobRepository(session).update_worker_heartbeat(
                worker_id=self.worker_id,
                status=status,
                current_job_id=current_job_id,
                increment_processed=increment_processed,
            )
            await session.commit()

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return classify_job_error(error) == JobErrorClassification.RETRYABLE

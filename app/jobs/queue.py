from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import JobAttemptStatus, JobStatus, JobType
from app.core.exceptions import JobNotFoundError, PersistenceError
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.integrity import get_constraint_name
from app.database.models import BackgroundJobModel, JobAttemptModel
from app.jobs.definitions import JobPayload, LeasedJob, validate_job_payload
from app.observability.context import get_context_value
from app.observability.metrics import (
    JOBS_DEAD_LETTER,
    JOBS_ENQUEUED,
    JOBS_FAILED,
    JOBS_STARTED,
    JOBS_SUCCEEDED,
)
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobAttemptRead, JobRead

logger = structlog.get_logger()


class JobQueue:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = JobRepository(session)

    async def enqueue(
        self,
        job_type: JobType,
        payload: JobPayload | BaseModel | dict[str, object],
        *,
        created_by: str,
        priority: int = 50,
        max_attempts: int | None = None,
        available_at: datetime | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        commit: bool = True,
    ) -> JobRead:
        raw_payload = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else payload
        )
        typed = validate_job_payload(job_type, raw_payload)
        safe_payload = sanitize_json(typed.model_dump(mode="json"))
        if not isinstance(safe_payload, dict):
            raise PersistenceError("Unable to prepare job payload")
        key = idempotency_key or self.build_idempotency_key(job_type, safe_payload)
        correlation = (
            correlation_id or get_context_value("correlation_id") or str(uuid4())
        )
        trace = trace_id or get_context_value("trace_id")
        try:
            async with self.session.begin_nested():
                model = await self.repository.create(
                    job_type=job_type,
                    payload=safe_payload,
                    priority=min(max(priority, 0), 100),
                    max_attempts=max_attempts or self.settings.job_max_attempts,
                    available_at=available_at or datetime.now(UTC),
                    idempotency_key=key,
                    correlation_id=correlation,
                    trace_id=trace,
                    created_by=sanitize_text(created_by, max_characters=200),
                )
        except IntegrityError as exc:
            if get_constraint_name(exc) != "uq_background_jobs_idempotency":
                if commit:
                    await self.session.rollback()
                raise PersistenceError("Unable to persist background job") from exc
            duplicate = await self.repository.find_by_idempotency_key(key)
            if duplicate is None:
                raise PersistenceError(
                    "Unable to load idempotent background job"
                ) from exc
            if commit:
                await self.session.commit()
            return job_to_schema(duplicate)
        if commit:
            await self.session.commit()
        logger.info(
            "job_enqueued" if commit else "job_enqueue_staged",
            job_id=str(model.job_id),
            job_type=model.job_type,
            correlation_id=model.correlation_id,
        )
        if commit:
            JOBS_ENQUEUED.labels(job_type.value).inc()
        return job_to_schema(model)

    async def get(self, job_id: UUID) -> JobRead:
        model = await self.repository.get_by_id(job_id, with_attempts=True)
        if model is None:
            raise JobNotFoundError("Background job not found")
        await self.session.commit()
        return job_to_schema(model, attempts=model.attempts)

    async def list_jobs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
    ) -> list[JobRead]:
        models = await self.repository.list(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            status=status,
            job_type=job_type,
        )
        await self.session.commit()
        return [job_to_schema(model) for model in models]

    async def lease(
        self, *, worker_id: str, limit: int | None = None
    ) -> list[LeasedJob]:
        models = await self.repository.lease_batch(
            worker_id=worker_id,
            limit=min(max(limit or self.settings.job_batch_size, 1), 100),
            lease_seconds=self.settings.job_lease_seconds,
        )
        leased: list[LeasedJob] = []
        for model in models:
            try:
                job_type = JobType(model.job_type)
            except ValueError:
                await self.repository.fail(
                    model.job_id,
                    worker_id=worker_id,
                    error_code="UNKNOWN_JOB_TYPE",
                    error_message="Background job type is not supported",
                    retryable=False,
                    retry_base_seconds=self.settings.job_retry_base_seconds,
                    retry_max_seconds=self.settings.job_retry_max_seconds,
                )
                logger.error(
                    "job_unknown_type",
                    job_id=str(model.job_id),
                    worker_id=worker_id,
                )
                continue
            leased.append(
                LeasedJob(
                    job_id=model.job_id,
                    job_type=job_type,
                    payload=model.payload,
                    attempt_count=model.attempt_count,
                    max_attempts=model.max_attempts,
                    correlation_id=model.correlation_id,
                    trace_id=model.trace_id,
                )
            )
        await self.session.commit()
        for job in leased:
            JOBS_STARTED.labels(job.job_type.value).inc()
            logger.info(
                "job_leased",
                job_id=str(job.job_id),
                job_type=job.job_type.value,
                worker_id=worker_id,
                correlation_id=job.correlation_id,
            )
        return leased

    async def heartbeat(self, job_id: UUID, *, worker_id: str) -> bool:
        renewed = await self.repository.heartbeat(
            job_id,
            worker_id=worker_id,
            lease_seconds=self.settings.job_lease_seconds,
        )
        await self.session.commit()
        return renewed

    async def complete(self, job_id: UUID, *, worker_id: str) -> JobRead:
        model = await self.repository.complete(job_id, worker_id=worker_id)
        await self.session.commit()
        logger.info("job_succeeded", job_id=str(job_id), worker_id=worker_id)
        JOBS_SUCCEEDED.labels(model.job_type).inc()
        return job_to_schema(model)

    async def fail(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> JobRead:
        model = await self.repository.fail(
            job_id,
            worker_id=worker_id,
            error_code=sanitize_text(error_code, max_characters=100),
            error_message=sanitize_text(error_message, max_characters=2000),
            retryable=retryable,
            retry_base_seconds=self.settings.job_retry_base_seconds,
            retry_max_seconds=self.settings.job_retry_max_seconds,
        )
        await self.session.commit()
        logger.warning(
            "job_failed",
            job_id=str(job_id),
            worker_id=worker_id,
            status=model.status,
            error_code=model.error_code,
        )
        JOBS_FAILED.labels(model.job_type, model.status).inc()
        if model.status == JobStatus.DEAD_LETTER.value:
            JOBS_DEAD_LETTER.labels(model.job_type).inc()
        return job_to_schema(model)

    async def cancel(self, job_id: UUID) -> JobRead:
        model = await self.repository.cancel(job_id)
        await self.session.commit()
        return job_to_schema(model)

    async def mark_cancelled(self, job_id: UUID, *, worker_id: str) -> JobRead:
        model = await self.repository.mark_cancelled(job_id, worker_id=worker_id)
        await self.session.commit()
        return job_to_schema(model)

    async def retry(self, job_id: UUID) -> JobRead:
        model = await self.repository.retry(job_id)
        await self.session.commit()
        return job_to_schema(model)

    async def reclaim_stale(self, *, limit: int | None = None) -> list[JobRead]:
        models = await self.repository.reclaim_stale(
            limit=min(max(limit or self.settings.job_batch_size, 1), 100),
            retry_base_seconds=self.settings.job_retry_base_seconds,
            retry_max_seconds=self.settings.job_retry_max_seconds,
        )
        await self.session.commit()
        return [job_to_schema(model) for model in models]

    async def cancellation_requested(self, job_id: UUID, *, worker_id: str) -> bool:
        requested = await self.repository.cancellation_requested(
            job_id, worker_id=worker_id
        )
        await self.session.commit()
        return requested

    @staticmethod
    def build_idempotency_key(job_type: JobType, payload: dict[str, object]) -> str:
        normalized = json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        material = f"{job_type.value}|{normalized}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def job_to_schema(
    model: BackgroundJobModel, *, attempts: list[JobAttemptModel] | None = None
) -> JobRead:
    return JobRead(
        job_id=model.job_id,
        job_type=JobType(model.job_type),
        status=JobStatus(model.status),
        payload=model.payload,
        priority=model.priority,
        attempt_count=model.attempt_count,
        max_attempts=model.max_attempts,
        available_at=model.available_at,
        locked_by=model.locked_by,
        lease_expires_at=model.lease_expires_at,
        heartbeat_at=model.heartbeat_at,
        cancel_requested=model.cancel_requested,
        idempotency_key=model.idempotency_key,
        correlation_id=model.correlation_id,
        trace_id=model.trace_id,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_code=model.error_code,
        error_message=model.error_message,
        attempts=[attempt_to_schema(attempt) for attempt in attempts or []],
    )


def attempt_to_schema(model: JobAttemptModel) -> JobAttemptRead:
    return JobAttemptRead(
        job_attempt_id=model.job_attempt_id,
        attempt_number=model.attempt_number,
        worker_id=model.worker_id,
        status=JobAttemptStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        duration_ms=model.duration_ms,
        error_code=model.error_code,
        error_message=model.error_message,
    )

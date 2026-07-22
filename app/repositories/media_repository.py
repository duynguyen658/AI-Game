from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    BackgroundJobModel,
    MediaAssetModel,
    MediaGenerationAttemptModel,
    MediaReviewModel,
)
from app.core.constants import JobStatus, MediaAttemptStatus, MediaAttemptUpdateResult
from app.core.sanitization import sanitize_text


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_asset(self, model: MediaAssetModel) -> MediaAssetModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_asset(self, asset_id: UUID) -> MediaAssetModel | None:
        return await self.session.get(MediaAssetModel, asset_id)

    async def get_asset_for_update(self, asset_id: UUID) -> MediaAssetModel | None:
        return await self.session.scalar(
            select(MediaAssetModel)
            .where(MediaAssetModel.media_asset_id == asset_id)
            .with_for_update()
        )

    async def get_asset_by_idempotency(
        self, actor_id: str, idempotency_key: str
    ) -> MediaAssetModel | None:
        return await self.session.scalar(
            select(MediaAssetModel).where(
                MediaAssetModel.created_by == actor_id,
                MediaAssetModel.idempotency_key == idempotency_key,
            )
        )

    async def get_asset_by_task(self, task_run_id: UUID) -> MediaAssetModel | None:
        return await self.session.scalar(
            select(MediaAssetModel).where(MediaAssetModel.task_run_id == task_run_id)
        )

    async def list_assets(
        self,
        *,
        limit: int,
        offset: int,
        owner_id: str | None = None,
        asset_type: str | None = None,
        status: str | None = None,
        campaign_id: str | None = None,
    ) -> list[MediaAssetModel]:
        statement = select(MediaAssetModel)
        if owner_id is not None:
            statement = statement.where(MediaAssetModel.created_by == owner_id)
        if asset_type is not None:
            statement = statement.where(MediaAssetModel.asset_type == asset_type)
        if status is not None:
            statement = statement.where(MediaAssetModel.status == status)
        if campaign_id is not None:
            statement = statement.where(MediaAssetModel.campaign_id == campaign_id)
        result = await self.session.execute(
            statement.order_by(
                MediaAssetModel.created_at.desc(), MediaAssetModel.media_asset_id
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_attempt(
        self, model: MediaGenerationAttemptModel
    ) -> MediaGenerationAttemptModel:
        self.session.add(model)
        await self.session.flush()
        return model

    async def create_started_attempt(
        self,
        *,
        asset_id: UUID,
        provider: str,
        model: str,
        job_id: UUID,
        worker_id: str,
        job_attempt_number: int,
    ) -> MediaGenerationAttemptModel | None:
        asset = await self.get_asset_for_update(asset_id)
        if asset is None:
            return None
        attempt = MediaGenerationAttemptModel(
            media_asset_id=asset_id,
            job_id=job_id,
            worker_id=worker_id,
            job_attempt_number=job_attempt_number,
            attempt_number=await self.next_attempt_number(asset_id),
            provider=provider,
            model=model,
            status=MediaAttemptStatus.STARTED.value,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def next_attempt_number(self, asset_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(MediaGenerationAttemptModel.attempt_number)).where(
                MediaGenerationAttemptModel.media_asset_id == asset_id
            )
        )
        return int(current or 0) + 1

    async def get_attempt(self, attempt_id: UUID) -> MediaGenerationAttemptModel | None:
        return await self.session.get(MediaGenerationAttemptModel, attempt_id)

    async def get_attempt_for_update(
        self, attempt_id: UUID
    ) -> MediaGenerationAttemptModel | None:
        return await self.session.scalar(
            select(MediaGenerationAttemptModel)
            .where(MediaGenerationAttemptModel.attempt_id == attempt_id)
            .with_for_update()
        )

    async def find_active_attempts(
        self, *, asset_id: UUID | None = None, job_id: UUID | None = None
    ) -> list[MediaGenerationAttemptModel]:
        statement = select(MediaGenerationAttemptModel).where(
            MediaGenerationAttemptModel.status == MediaAttemptStatus.STARTED.value
        )
        if asset_id is not None:
            statement = statement.where(
                MediaGenerationAttemptModel.media_asset_id == asset_id
            )
        if job_id is not None:
            statement = statement.where(MediaGenerationAttemptModel.job_id == job_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def mark_completed(
        self,
        attempt_id: UUID,
        *,
        worker_id: str,
        provider_job_id: str | None,
        estimated_cost: float | Decimal | None,
    ) -> MediaAttemptUpdateResult:
        return await self._mark_terminal(
            attempt_id,
            status=MediaAttemptStatus.COMPLETED,
            worker_id=worker_id,
            provider_job_id=provider_job_id,
            estimated_cost=estimated_cost,
        )

    async def mark_failed(
        self,
        attempt_id: UUID,
        *,
        worker_id: str | None,
        error_code: str,
        error_message: str,
        provider_job_id: str | None = None,
        estimated_cost: float | Decimal | None = None,
    ) -> MediaAttemptUpdateResult:
        return await self._mark_terminal(
            attempt_id,
            status=MediaAttemptStatus.FAILED,
            worker_id=worker_id,
            error_code=error_code,
            error_message=error_message,
            provider_job_id=provider_job_id,
            estimated_cost=estimated_cost,
        )

    async def mark_cancelled(
        self,
        attempt_id: UUID,
        *,
        worker_id: str | None,
        error_code: str = "JOB_CANCELLED",
        error_message: str = "Media generation was cancelled",
        provider_job_id: str | None = None,
        estimated_cost: float | Decimal | None = None,
    ) -> MediaAttemptUpdateResult:
        return await self._mark_terminal(
            attempt_id,
            status=MediaAttemptStatus.CANCELLED,
            worker_id=worker_id,
            error_code=error_code,
            error_message=error_message,
            provider_job_id=provider_job_id,
            estimated_cost=estimated_cost,
        )

    async def terminalize_active_attempts(
        self,
        *,
        asset_id: UUID,
        status: MediaAttemptStatus,
        error_code: str,
        error_message: str,
    ) -> int:
        result = await self.session.execute(
            select(MediaGenerationAttemptModel)
            .where(
                MediaGenerationAttemptModel.media_asset_id == asset_id,
                MediaGenerationAttemptModel.status == MediaAttemptStatus.STARTED.value,
            )
            .with_for_update()
        )
        attempts = list(result.scalars().all())
        for attempt in attempts:
            self._apply_terminal_values(
                attempt,
                status=status,
                error_code=error_code,
                error_message=error_message,
            )
        await self.session.flush()
        return len(attempts)

    async def owns_live_job_lease(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        job_attempt_number: int,
    ) -> bool:
        job = await self.session.scalar(
            select(BackgroundJobModel)
            .where(BackgroundJobModel.job_id == job_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        return bool(
            job is not None
            and job.status == JobStatus.RUNNING.value
            and job.locked_by == worker_id
            and job.attempt_count == job_attempt_number
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )

    async def _mark_terminal(
        self,
        attempt_id: UUID,
        *,
        status: MediaAttemptStatus,
        worker_id: str | None,
        error_code: str | None = None,
        error_message: str | None = None,
        provider_job_id: str | None = None,
        estimated_cost: float | Decimal | None = None,
    ) -> MediaAttemptUpdateResult:
        attempt = await self.get_attempt_for_update(attempt_id)
        if attempt is None:
            return MediaAttemptUpdateResult.NOT_FOUND
        if worker_id is not None and attempt.worker_id != worker_id:
            return MediaAttemptUpdateResult.OWNERSHIP_LOST
        if attempt.status != MediaAttemptStatus.STARTED.value:
            return MediaAttemptUpdateResult.INVALID_STATE
        self._apply_terminal_values(
            attempt,
            status=status,
            error_code=error_code,
            error_message=error_message,
            provider_job_id=provider_job_id,
            estimated_cost=estimated_cost,
        )
        await self.session.flush()
        return MediaAttemptUpdateResult.UPDATED

    @staticmethod
    def _apply_terminal_values(
        attempt: MediaGenerationAttemptModel,
        *,
        status: MediaAttemptStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        provider_job_id: str | None = None,
        estimated_cost: float | Decimal | None = None,
    ) -> None:
        now = datetime.now(UTC)
        attempt.status = status.value
        attempt.completed_at = now
        attempt.duration_ms = max(
            int((now - attempt.started_at).total_seconds() * 1000), 0
        )
        attempt.error_code = error_code
        attempt.error_message = (
            sanitize_text(error_message, max_characters=2000) if error_message else None
        )
        attempt.provider_job_id = provider_job_id
        attempt.estimated_cost = (
            Decimal(str(estimated_cost)) if estimated_cost is not None else None
        )

    async def create_review(self, model: MediaReviewModel) -> MediaReviewModel:
        self.session.add(model)
        await self.session.flush()
        return model

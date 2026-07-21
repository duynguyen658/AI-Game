from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.constants import (
    AppliedTaskStatus,
    AppliedWorkflowType,
    JobType,
    MediaAssetStatus,
    MediaAssetType,
    MediaAttemptStatus,
    MediaAttemptUpdateResult,
    OutboxEventType,
    UserRole,
)
from app.core.exceptions import (
    ApplicationError,
    JobCancelledError,
    MediaAttemptFinalizationError,
    MediaAttemptLeaseLostError,
    MediaAttemptStateConflictError,
    MediaPersistenceError,
    M7ConflictError,
    M7ResourceNotFoundError,
    M7ValidationError,
)
from app.core.sanitization import sanitize_text
from app.database.models import (
    AppliedWorkflowTaskModel,
    MediaAssetModel,
    MediaReviewModel,
)
from app.database.m7_integrity import (
    MEDIA_ATTEMPT_NUMBER_CONSTRAINT,
    is_constraint,
    is_media_request_idempotency_conflict,
)
from app.jobs.definitions import (
    ImageGenerationJobPayload,
    LeasedJob,
    VideoStoryboardJobPayload,
)
from app.jobs.queue import JobQueue
from app.llm.base import LLMClient
from app.llm.capabilities import CompletionRequest, NormalizedCompletion
from app.media.definitions import (
    ImageGenerationInput,
    GeneratedImage,
)
from app.media.providers.base import ImageGenerationProvider
from app.media.providers.mock import MockImageProvider
from app.media.providers.real_image_provider import OpenAIImageProvider
from app.media.safety import validate_generated_image
from app.media.storage import LocalMediaStorage
from app.outbox.service import OutboxService
from app.observability.metrics import (
    BUSINESS_OUTPUT_ACCEPTANCE,
    MEDIA_ATTEMPT_FINALIZATION_FAILURES,
    MEDIA_ATTEMPT_OWNERSHIP_LOST,
    MEDIA_ATTEMPTS,
    PERSISTENCE_CONSTRAINT_CONFLICTS,
    PERSISTENCE_UNKNOWN_CONSTRAINT_FAILURES,
)
from app.prompt_management.execution import model_configuration_hash
from app.prompt_management.renderer import PromptRenderer
from app.prompt_management.service import PromptService
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.repositories.business_impact_repository import BusinessImpactRepository
from app.repositories.media_repository import MediaRepository
from app.repositories.prompt_repository import PromptRepository
from app.schemas.media import (
    ImageGenerationRequest,
    MediaAssetRead,
    MediaReviewRequest,
    VideoStoryboard,
    VideoStoryboardRequest,
)
from app.service.auth_service import AuthenticatedActor

logger = structlog.get_logger()


class MediaService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.media = MediaRepository(session)
        self.tasks = AppliedWorkflowRepository(session)

    async def request_image(
        self,
        data: ImageGenerationRequest,
        *,
        actor: AuthenticatedActor,
        idempotency_key: str | None = None,
    ) -> MediaAssetRead:
        if idempotency_key:
            idempotency_key = sanitize_text(idempotency_key, max_characters=200)
            existing = await self.media.get_asset_by_idempotency(
                actor.actor_id, idempotency_key
            )
            if existing is not None:
                return media_to_schema(existing)
        managed = await PromptService(self.session).resolve(
            values={"brief": data.prompt}, task_type="image_generation"
        )
        configuration_hash = model_configuration_hash(
            self.settings.image_provider,
            self.settings.image_model,
            {"width": data.width, "height": data.height},
        )
        task = AppliedWorkflowTaskModel(
            workflow_type=AppliedWorkflowType.IMAGE_GENERATION.value,
            status=AppliedTaskStatus.PENDING.value,
            input_metadata=data.model_dump(mode="json"),
            provider=self.settings.image_provider,
            model=self.settings.image_model,
            prompt_template_id=managed.prompt_template_id,
            prompt_version_id=managed.prompt_version_id,
            prompt_version_number=managed.prompt_version_number,
            prompt_content_hash=managed.content_hash,
            model_configuration_hash=configuration_hash,
            application_version=self.settings.application_version,
            created_by=actor.actor_id,
        )
        await self.tasks.create(task)
        asset = MediaAssetModel(
            campaign_id=data.campaign_id,
            workflow_id=data.workflow_id,
            task_run_id=task.task_run_id,
            task_type=data.task_type,
            asset_type=MediaAssetType.IMAGE.value,
            status=MediaAssetStatus.REQUESTED.value,
            provider=self.settings.image_provider,
            model=self.settings.image_model,
            prompt_template_id=managed.prompt_template_id,
            prompt_version_id=managed.prompt_version_id,
            prompt_version_number=managed.prompt_version_number,
            prompt_content_hash=managed.content_hash,
            model_configuration_hash=configuration_hash,
            application_version=self.settings.application_version,
            generation_prompt=sanitize_text(managed.user_prompt, max_characters=10_000),
            negative_prompt=(
                sanitize_text(data.negative_prompt, max_characters=3000)
                if data.negative_prompt
                else None
            ),
            width=data.width,
            height=data.height,
            safety_status="PENDING",
            created_by=actor.actor_id,
            idempotency_key=idempotency_key,
        )
        try:
            await self.media.create_asset(asset)
            job = await JobQueue(self.session, settings=self.settings).enqueue(
                JobType.IMAGE_GENERATION,
                ImageGenerationJobPayload(media_asset_id=asset.media_asset_id),
                created_by=actor.actor_id,
                idempotency_key=f"image-generation:{actor.actor_id}:{idempotency_key}"
                if idempotency_key
                else f"image-generation:{asset.media_asset_id}",
                commit=False,
            )
            task.job_id = job.job_id
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if idempotency_key and is_media_request_idempotency_conflict(exc):
                PERSISTENCE_CONSTRAINT_CONFLICTS.labels("media_idempotency").inc()
                existing = await self.media.get_asset_by_idempotency(
                    actor.actor_id, idempotency_key
                )
                if existing is not None:
                    return media_to_schema(existing)
                raise M7ConflictError("Image request already exists") from exc
            PERSISTENCE_UNKNOWN_CONSTRAINT_FAILURES.labels("media_request").inc()
            logger.exception("unknown_constraint_failure", operation="media_request")
            raise MediaPersistenceError("Unable to persist image request") from exc
        return media_to_schema(asset)

    async def request_storyboard(
        self, data: VideoStoryboardRequest, *, actor: AuthenticatedActor
    ) -> MediaAssetRead:
        managed = await PromptService(self.session).resolve(
            values={"brief": data.campaign_brief}, task_type="video_storyboard"
        )
        model_name = self.settings.llm_model or "mock-applied-ai"
        configuration_hash = model_configuration_hash(
            self.settings.llm_provider, model_name, {"temperature": 0}
        )
        task = AppliedWorkflowTaskModel(
            workflow_type=AppliedWorkflowType.VIDEO_STORYBOARD.value,
            status=AppliedTaskStatus.PENDING.value,
            input_metadata=data.model_dump(mode="json"),
            provider=self.settings.llm_provider,
            model=model_name,
            prompt_template_id=managed.prompt_template_id,
            prompt_version_id=managed.prompt_version_id,
            prompt_version_number=managed.prompt_version_number,
            prompt_content_hash=managed.content_hash,
            model_configuration_hash=configuration_hash,
            application_version=self.settings.application_version,
            created_by=actor.actor_id,
        )
        await self.tasks.create(task)
        asset = MediaAssetModel(
            campaign_id=data.campaign_id,
            task_run_id=task.task_run_id,
            task_type="video_storyboard",
            asset_type=MediaAssetType.VIDEO_STORYBOARD.value,
            status=MediaAssetStatus.REQUESTED.value,
            provider=self.settings.llm_provider,
            model=model_name,
            prompt_template_id=managed.prompt_template_id,
            prompt_version_id=managed.prompt_version_id,
            prompt_version_number=managed.prompt_version_number,
            prompt_content_hash=managed.content_hash,
            model_configuration_hash=configuration_hash,
            application_version=self.settings.application_version,
            generation_prompt=managed.user_prompt,
            duration_seconds=data.target_duration_seconds,
            safety_status="NOT_APPLICABLE",
            created_by=actor.actor_id,
        )
        await self.media.create_asset(asset)
        job = await JobQueue(self.session, settings=self.settings).enqueue(
            JobType.VIDEO_STORYBOARD,
            VideoStoryboardJobPayload(media_asset_id=asset.media_asset_id),
            created_by=actor.actor_id,
            idempotency_key=f"video-storyboard:{asset.media_asset_id}",
            commit=False,
        )
        task.job_id = job.job_id
        await self.session.commit()
        return media_to_schema(asset)

    async def get(self, asset_id: UUID) -> MediaAssetRead:
        return media_to_schema(await self._asset(asset_id))

    async def review(
        self,
        asset_id: UUID,
        data: MediaReviewRequest,
        *,
        actor: AuthenticatedActor,
    ) -> MediaAssetRead:
        if actor.role not in {UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN}:
            raise M7ConflictError("Reviewer role is required")
        asset = await self.media.get_asset_for_update(asset_id)
        if asset is None:
            raise M7ResourceNotFoundError("Media asset not found")
        if asset.status != MediaAssetStatus.READY_FOR_REVIEW.value:
            raise M7ConflictError("Media asset is not ready for review")
        now = datetime.now(UTC)
        if data.decision == "APPROVE":
            asset.status = MediaAssetStatus.APPROVED.value
            asset.approved_by = actor.actor_id
            asset.approved_at = now
            event = OutboxEventType.MEDIA_APPROVED
        else:
            if not data.comment:
                raise M7ValidationError("A rejection reason is required")
            asset.status = MediaAssetStatus.REJECTED.value
            asset.rejected_by = actor.actor_id
            asset.rejected_at = now
            asset.rejection_reason = sanitize_text(data.comment, max_characters=1000)
            event = OutboxEventType.MEDIA_REJECTED
        acceptance_recorded = False
        if asset.task_run_id is not None:
            impact = await BusinessImpactRepository(self.session).get_impact_by_task(
                asset.task_run_id
            )
            if impact is not None:
                impact.output_accepted = data.decision == "APPROVE"
                acceptance_recorded = True
                if data.decision != "APPROVE":
                    impact.accepted_without_editing = False
        await self.media.create_review(
            MediaReviewModel(
                media_asset_id=asset_id,
                actor_id=actor.actor_id,
                decision=data.decision,
                rating=data.rating,
                comment=(
                    sanitize_text(data.comment, max_characters=2000)
                    if data.comment
                    else None
                ),
            )
        )
        await OutboxService(self.session).add_event(
            event_type=event,
            aggregate_type="media_asset",
            aggregate_id=str(asset_id),
            payload={"media_asset_id": str(asset_id), "decision": data.decision},
            idempotency_key=f"media-review:{asset_id}:{data.decision}",
        )
        await self.session.commit()
        if acceptance_recorded:
            decision = "accepted" if data.decision == "APPROVE" else "rejected"
            BUSINESS_OUTPUT_ACCEPTANCE.labels(decision).inc()
            logger.info("business_output_acceptance_recorded", decision=decision)
        return media_to_schema(asset)

    async def _asset(self, asset_id: UUID) -> MediaAssetModel:
        model = await self.media.get_asset(asset_id)
        if model is None:
            raise M7ResourceNotFoundError("Media asset not found")
        return model


class MediaProcessor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        settings: Settings,
        llm_client: LLMClient,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.llm_client = llm_client

    async def generate_image(
        self,
        asset_id: UUID,
        *,
        job: LeasedJob,
        worker_id: str,
        checkpoint: Callable[[], Awaitable[None]],
    ) -> None:
        started = await self._start_attempt(asset_id, job=job, worker_id=worker_id)
        if started is None:
            return
        attempt_id, prompt, provider_name, model, negative_prompt, width, height = (
            started
        )
        provider_job_id: str | None = None
        estimated_cost: float | None = None
        try:
            provider = self._image_provider(provider_name)
            generated = await provider.generate(
                ImageGenerationInput(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    model=model,
                )
            )
            provider_job_id = generated.provider_job_id
            estimated_cost = generated.estimated_cost
            validate_generated_image(generated)
            if generated.estimated_cost > self.settings.media_max_cost:
                raise M7ValidationError(
                    "Image generation exceeded the configured cost limit"
                )
            storage_uri = LocalMediaStorage(self.settings.media_storage_root).store(
                asset_id, generated.content, generated.mime_type
            )
            await checkpoint()
            await self._finalize_image_success(
                asset_id,
                attempt_id=attempt_id,
                job=job,
                worker_id=worker_id,
                storage_uri=storage_uri,
                generated=generated,
            )
        except (asyncio.CancelledError, JobCancelledError):
            await asyncio.shield(
                self._finish_attempt(
                    attempt_id,
                    MediaAttemptStatus.CANCELLED,
                    worker_id=worker_id,
                    provider_job_id=provider_job_id,
                    estimated_cost=estimated_cost,
                )
            )
            raise
        except Exception as exc:
            await self._finish_attempt(
                attempt_id,
                MediaAttemptStatus.FAILED,
                worker_id=worker_id,
                error=exc,
                provider_job_id=provider_job_id,
                estimated_cost=estimated_cost,
            )
            raise

    async def _finalize_image_success(
        self,
        asset_id: UUID,
        *,
        attempt_id: UUID,
        job: LeasedJob,
        worker_id: str,
        storage_uri: str,
        generated: GeneratedImage,
    ) -> None:
        image = generated
        async with self.session_factory() as session:
            service = MediaService(session, settings=self.settings)
            if not await service.media.owns_live_job_lease(
                job_id=job.job_id,
                worker_id=worker_id,
                job_attempt_number=job.attempt_count,
            ):
                MEDIA_ATTEMPT_OWNERSHIP_LOST.inc()
                logger.warning("media_attempt_ownership_lost", operation="image")
                raise MediaAttemptLeaseLostError("Media job lease is no longer owned")
            asset = await service.media.get_asset_for_update(asset_id)
            attempt = await service.media.get_attempt_for_update(attempt_id)
            if asset is None or attempt is None:
                raise MediaAttemptFinalizationError(
                    "Media finalization target is missing"
                )
            if (
                attempt.status != MediaAttemptStatus.STARTED.value
                or attempt.worker_id != worker_id
                or attempt.job_id != job.job_id
                or attempt.job_attempt_number != job.attempt_count
                or attempt.attempt_number != job.attempt_count
            ):
                raise MediaAttemptStateConflictError(
                    "Media attempt changed before finalization"
                )
            if asset.status != MediaAssetStatus.GENERATING.value:
                raise MediaAttemptStateConflictError(
                    "Media asset changed before finalization"
                )
            asset.status = MediaAssetStatus.READY_FOR_REVIEW.value
            asset.storage_uri = storage_uri
            asset.mime_type = image.mime_type
            asset.width = image.width
            asset.height = image.height
            asset.estimated_cost = Decimal(str(image.estimated_cost))
            asset.safety_status = "PASSED_PROVIDER_AND_DETERMINISTIC_CHECKS"
            asset.completed_at = datetime.now(UTC)
            task = (
                await AppliedWorkflowRepository(session).get_for_update(
                    asset.task_run_id
                )
                if asset.task_run_id
                else None
            )
            if task is not None:
                if task.status != AppliedTaskStatus.PROCESSING.value:
                    raise MediaAttemptStateConflictError(
                        "Media task changed before finalization"
                    )
                task.status = AppliedTaskStatus.COMPLETED.value
                task.result = media_to_schema(asset).model_dump(mode="json")
                task.completed_at = datetime.now(UTC)
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
                task.estimated_cost = Decimal(str(image.estimated_cost))
            update_result = await service.media.mark_completed(
                attempt_id,
                worker_id=worker_id,
                provider_job_id=image.provider_job_id,
                estimated_cost=image.estimated_cost,
            )
            if update_result != MediaAttemptUpdateResult.UPDATED:
                raise MediaAttemptStateConflictError(
                    "Media attempt could not be completed"
                )
            await OutboxService(session).add_event(
                event_type=OutboxEventType.MEDIA_READY_FOR_REVIEW,
                aggregate_type="media_asset",
                aggregate_id=str(asset_id),
                payload={"media_asset_id": str(asset_id)},
                idempotency_key=f"media-ready:{asset_id}",
            )
            await session.commit()
            MEDIA_ATTEMPTS.labels("image", MediaAttemptStatus.COMPLETED.value).inc()
            logger.info("media_attempt_completed", operation="image")

    async def generate_storyboard(
        self,
        asset_id: UUID,
        *,
        job: LeasedJob,
        worker_id: str,
        checkpoint: Callable[[], Awaitable[None]],
    ) -> None:
        async with self.session_factory() as session:
            try:
                asset = await MediaRepository(session).get_asset_for_update(asset_id)
                if asset is None:
                    raise M7ResourceNotFoundError("Media asset not found")
                if asset.status == MediaAssetStatus.READY_FOR_REVIEW.value:
                    return
                task = (
                    await AppliedWorkflowRepository(session).get(asset.task_run_id)
                    if asset.task_run_id
                    else None
                )
                if task is None:
                    raise M7ResourceNotFoundError("Storyboard task not found")
                request = VideoStoryboardRequest.model_validate(task.input_metadata)
                prompt_version = (
                    await PromptRepository(session).get_version(asset.prompt_version_id)
                    if asset.prompt_version_id
                    else None
                )
                if prompt_version is None:
                    raise M7ResourceNotFoundError("Managed storyboard prompt not found")
                asset.status = MediaAssetStatus.GENERATING.value
                task.status = AppliedTaskStatus.PROCESSING.value
                task.started_at = task.started_at or datetime.now(UTC)
                attempt = await MediaRepository(session).create_started_attempt(
                    asset_id=asset_id,
                    provider=asset.provider,
                    model=asset.model,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    job_attempt_number=job.attempt_count,
                )
                if attempt is None:
                    raise M7ResourceNotFoundError("Media asset not found")
                attempt_id = attempt.attempt_id
                await session.commit()
                MEDIA_ATTEMPTS.labels(
                    "storyboard", MediaAttemptStatus.STARTED.value
                ).inc()
                logger.info("media_attempt_started", operation="storyboard")
            except IntegrityError as exc:
                await session.rollback()
                if is_constraint(exc, MEDIA_ATTEMPT_NUMBER_CONSTRAINT):
                    PERSISTENCE_CONSTRAINT_CONFLICTS.labels(
                        "media_attempt_number"
                    ).inc()
                    raise MediaAttemptStateConflictError(
                        "Media attempt number changed; retry the job"
                    ) from exc
                PERSISTENCE_UNKNOWN_CONSTRAINT_FAILURES.labels("media_attempt").inc()
                logger.exception(
                    "unknown_constraint_failure", operation="storyboard_attempt"
                )
                raise MediaPersistenceError("Unable to persist media attempt") from exc
        estimated_cost: float | None = None
        try:
            completion = await self.llm_client.complete_structured(
                CompletionRequest(
                    system_prompt=prompt_version.system_prompt,
                    user_prompt=PromptRenderer().render(
                        prompt_version.user_prompt_template,
                        {"brief": request.campaign_brief},
                        allowed_variables={
                            key
                            for key in prompt_version.variables
                            if not key.startswith("__")
                        },
                        allow_unknown=bool(
                            prompt_version.variables.get("__allow_unknown__", False)
                        ),
                    ),
                    model=self.settings.llm_model or "mock-applied-ai",
                ),
                VideoStoryboard,
            )
            storyboard = VideoStoryboard.model_validate(completion.structured)
            estimated_cost = completion.usage.estimated_cost
            await checkpoint()
            await self._finalize_storyboard_success(
                asset_id,
                attempt_id=attempt_id,
                job=job,
                worker_id=worker_id,
                storyboard=storyboard,
                completion=completion,
            )
        except (asyncio.CancelledError, JobCancelledError):
            await asyncio.shield(
                self._finish_attempt(
                    attempt_id,
                    MediaAttemptStatus.CANCELLED,
                    worker_id=worker_id,
                    estimated_cost=estimated_cost,
                )
            )
            raise
        except Exception as exc:
            await self._finish_attempt(
                attempt_id,
                MediaAttemptStatus.FAILED,
                worker_id=worker_id,
                error=exc,
                estimated_cost=estimated_cost,
            )
            raise

    async def _finalize_storyboard_success(
        self,
        asset_id: UUID,
        *,
        attempt_id: UUID,
        job: LeasedJob,
        worker_id: str,
        storyboard: VideoStoryboard,
        completion: NormalizedCompletion,
    ) -> None:
        result = completion
        async with self.session_factory() as session:
            service = MediaService(session, settings=self.settings)
            if not await service.media.owns_live_job_lease(
                job_id=job.job_id,
                worker_id=worker_id,
                job_attempt_number=job.attempt_count,
            ):
                MEDIA_ATTEMPT_OWNERSHIP_LOST.inc()
                logger.warning("media_attempt_ownership_lost", operation="storyboard")
                raise MediaAttemptLeaseLostError("Media job lease is no longer owned")
            asset = await service.media.get_asset_for_update(asset_id)
            attempt = await service.media.get_attempt_for_update(attempt_id)
            if asset is None or attempt is None:
                raise MediaAttemptFinalizationError(
                    "Media finalization target is missing"
                )
            if (
                attempt.status != MediaAttemptStatus.STARTED.value
                or attempt.worker_id != worker_id
                or attempt.job_id != job.job_id
                or attempt.job_attempt_number != job.attempt_count
                or attempt.attempt_number != job.attempt_count
            ):
                raise MediaAttemptStateConflictError(
                    "Media attempt changed before finalization"
                )
            if asset.status != MediaAssetStatus.GENERATING.value:
                raise MediaAttemptStateConflictError(
                    "Media asset changed before finalization"
                )
            asset.status = MediaAssetStatus.READY_FOR_REVIEW.value
            asset.safety_status = "READY_FOR_HUMAN_REVIEW"
            task = (
                await AppliedWorkflowRepository(session).get_for_update(
                    asset.task_run_id
                )
                if asset.task_run_id
                else None
            )
            if task is not None:
                if task.status != AppliedTaskStatus.PROCESSING.value:
                    raise MediaAttemptStateConflictError(
                        "Media task changed before finalization"
                    )
                task.status = AppliedTaskStatus.COMPLETED.value
                task.result = storyboard.model_dump(mode="json")
                task.input_tokens = result.usage.input_tokens
                task.output_tokens = result.usage.output_tokens
                task.estimated_cost = Decimal(str(result.usage.estimated_cost))
                task.completed_at = datetime.now(UTC)
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
            asset.completed_at = datetime.now(UTC)
            update_result = await service.media.mark_completed(
                attempt_id,
                worker_id=worker_id,
                provider_job_id=None,
                estimated_cost=result.usage.estimated_cost,
            )
            if update_result != MediaAttemptUpdateResult.UPDATED:
                raise MediaAttemptStateConflictError(
                    "Media attempt could not be completed"
                )
            await OutboxService(session).add_event(
                event_type=OutboxEventType.MEDIA_READY_FOR_REVIEW,
                aggregate_type="media_asset",
                aggregate_id=str(asset_id),
                payload={
                    "media_asset_id": str(asset_id),
                    "asset_type": "VIDEO_STORYBOARD",
                },
                idempotency_key=f"media-ready:{asset_id}",
            )
            await session.commit()
            MEDIA_ATTEMPTS.labels(
                "storyboard", MediaAttemptStatus.COMPLETED.value
            ).inc()
            logger.info("media_attempt_completed", operation="storyboard")

    async def _start_attempt(
        self, asset_id: UUID, *, job: LeasedJob, worker_id: str
    ) -> tuple[UUID, str, str, str, str | None, int, int] | None:
        for allocation_try in range(2):
            async with self.session_factory() as session:
                repository = MediaRepository(session)
                try:
                    asset = await repository.get_asset_for_update(asset_id)
                    if asset is None:
                        raise M7ResourceNotFoundError("Media asset not found")
                    if asset.status in {
                        MediaAssetStatus.READY_FOR_REVIEW.value,
                        MediaAssetStatus.APPROVED.value,
                    }:
                        return None
                    asset.status = MediaAssetStatus.GENERATING.value
                    asset.error_code = None
                    asset.error_message = None
                    task = (
                        await AppliedWorkflowRepository(session).get_for_update(
                            asset.task_run_id
                        )
                        if asset.task_run_id
                        else None
                    )
                    if task is not None:
                        task.status = AppliedTaskStatus.PROCESSING.value
                        task.started_at = task.started_at or datetime.now(UTC)
                    attempt = await repository.create_started_attempt(
                        asset_id=asset_id,
                        provider=asset.provider,
                        model=asset.model,
                        job_id=job.job_id,
                        worker_id=worker_id,
                        job_attempt_number=job.attempt_count,
                    )
                    if attempt is None:
                        raise M7ResourceNotFoundError("Media asset not found")
                    await session.commit()
                    MEDIA_ATTEMPTS.labels(
                        "image", MediaAttemptStatus.STARTED.value
                    ).inc()
                    logger.info("media_attempt_started", operation="image")
                    return (
                        attempt.attempt_id,
                        asset.generation_prompt,
                        asset.provider,
                        asset.model,
                        asset.negative_prompt,
                        asset.width or 1024,
                        asset.height or 1024,
                    )
                except IntegrityError as exc:
                    await session.rollback()
                    if is_constraint(exc, MEDIA_ATTEMPT_NUMBER_CONSTRAINT):
                        PERSISTENCE_CONSTRAINT_CONFLICTS.labels(
                            "media_attempt_number"
                        ).inc()
                        if allocation_try == 0:
                            continue
                        raise MediaAttemptStateConflictError(
                            "Media attempt number changed; retry the job"
                        ) from exc
                    PERSISTENCE_UNKNOWN_CONSTRAINT_FAILURES.labels(
                        "media_attempt"
                    ).inc()
                    logger.exception(
                        "unknown_constraint_failure", operation="media_attempt"
                    )
                    raise MediaPersistenceError(
                        "Unable to persist media attempt"
                    ) from exc
        raise MediaAttemptStateConflictError("Unable to allocate media attempt")

    async def _finish_attempt(
        self,
        attempt_id: UUID,
        status: MediaAttemptStatus,
        *,
        worker_id: str,
        error: Exception | None = None,
        provider_job_id: str | None = None,
        estimated_cost: float | None = None,
    ) -> None:
        code, message = _safe_media_error(error, status=status)
        try:
            async with self.session_factory() as session:
                repository = MediaRepository(session)
                if status == MediaAttemptStatus.CANCELLED:
                    result = await repository.mark_cancelled(
                        attempt_id,
                        worker_id=worker_id,
                        error_code=code,
                        error_message=message,
                        provider_job_id=provider_job_id,
                        estimated_cost=estimated_cost,
                    )
                else:
                    result = await repository.mark_failed(
                        attempt_id,
                        worker_id=worker_id,
                        error_code=code,
                        error_message=message,
                        provider_job_id=provider_job_id,
                        estimated_cost=estimated_cost,
                    )
                if result == MediaAttemptUpdateResult.OWNERSHIP_LOST:
                    MEDIA_ATTEMPT_OWNERSHIP_LOST.inc()
                    logger.warning("media_attempt_ownership_lost", operation="cleanup")
                    return
                await session.commit()
                if result == MediaAttemptUpdateResult.UPDATED:
                    asset_type = "media"
                    MEDIA_ATTEMPTS.labels(asset_type, status.value).inc()
                    logger.info(
                        f"media_attempt_{status.value.lower()}", operation=asset_type
                    )
        except Exception as finalization_error:
            MEDIA_ATTEMPT_FINALIZATION_FAILURES.inc()
            logger.exception("media_attempt_terminalization_failed")
            raise MediaAttemptFinalizationError(
                "Unable to terminalize media attempt"
            ) from finalization_error

    def _image_provider(self, provider: str) -> ImageGenerationProvider:
        if provider == "mock":
            return MockImageProvider()
        if provider == "openai":
            return OpenAIImageProvider(self.settings)
        raise M7ValidationError("Image provider is not configured")


def media_to_schema(model: MediaAssetModel) -> MediaAssetRead:
    return MediaAssetRead.model_validate(model, from_attributes=True)


def _safe_media_error(
    error: Exception | None, *, status: MediaAttemptStatus
) -> tuple[str, str]:
    if status == MediaAttemptStatus.CANCELLED:
        return "JOB_CANCELLED", "Media generation was cancelled"
    if isinstance(error, ApplicationError):
        return error.error_code, sanitize_text(error.message, max_characters=2000)
    return "MEDIA_ERROR", "Media generation failed"


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int:
    if started_at is None:
        return 0
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)

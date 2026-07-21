from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.constants import (
    AppliedTaskStatus,
    AppliedWorkflowType,
    JobType,
    MediaAssetStatus,
    MediaAssetType,
    OutboxEventType,
    UserRole,
)
from app.core.exceptions import (
    ApplicationError,
    M7ConflictError,
    M7ResourceNotFoundError,
    M7ValidationError,
)
from app.core.sanitization import sanitize_text
from app.database.models import (
    AppliedWorkflowTaskModel,
    MediaAssetModel,
    MediaGenerationAttemptModel,
    MediaReviewModel,
)
from app.jobs.definitions import ImageGenerationJobPayload, VideoStoryboardJobPayload
from app.jobs.queue import JobQueue
from app.llm.base import LLMClient
from app.llm.capabilities import CompletionRequest
from app.media.definitions import ImageGenerationInput
from app.media.providers.base import ImageGenerationProvider
from app.media.providers.mock import MockImageProvider
from app.media.providers.real_image_provider import OpenAIImageProvider
from app.media.safety import validate_generated_image
from app.media.storage import LocalMediaStorage
from app.outbox.service import OutboxService
from app.prompt_management.execution import model_configuration_hash
from app.prompt_management.renderer import PromptRenderer
from app.prompt_management.service import PromptService
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
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
            if idempotency_key:
                existing = await self.media.get_asset_by_idempotency(
                    actor.actor_id, idempotency_key
                )
                if existing is not None:
                    return media_to_schema(existing)
            raise M7ConflictError("Image request already exists") from exc
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

    async def generate_image(self, asset_id: UUID) -> None:
        attempt_id: UUID
        async with self.session_factory() as session:
            asset = await MediaService(session, settings=self.settings)._asset(asset_id)
            if asset.status in {
                MediaAssetStatus.READY_FOR_REVIEW.value,
                MediaAssetStatus.APPROVED.value,
            }:
                return
            prompt = asset.generation_prompt
            negative_prompt = asset.negative_prompt
            width = asset.width or 1024
            height = asset.height or 1024
            model = asset.model
            provider_name = asset.provider
            asset.status = MediaAssetStatus.GENERATING.value
            asset.error_code = None
            asset.error_message = None
            task = (
                await AppliedWorkflowRepository(session).get(asset.task_run_id)
                if asset.task_run_id
                else None
            )
            if task is not None:
                task.status = AppliedTaskStatus.PROCESSING.value
                task.started_at = task.started_at or datetime.now(UTC)
            attempt = await MediaRepository(session).create_attempt(
                MediaGenerationAttemptModel(
                    media_asset_id=asset_id,
                    attempt_number=await MediaRepository(session).next_attempt_number(
                        asset_id
                    ),
                    provider=provider_name,
                    model=model,
                    status="STARTED",
                )
            )
            attempt_id = attempt.attempt_id
            await session.commit()
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
            validate_generated_image(generated)
            if generated.estimated_cost > self.settings.media_max_cost:
                raise M7ValidationError(
                    "Image generation exceeded the configured cost limit"
                )
            storage_uri = LocalMediaStorage(self.settings.media_storage_root).store(
                asset_id, generated.content, generated.mime_type
            )
        except asyncio.CancelledError:
            await self._finish_attempt(attempt_id, "CANCELLED")
            raise
        except Exception as exc:
            await self._finish_attempt(attempt_id, "FAILED", error=exc)
            raise
        async with self.session_factory() as session:
            service = MediaService(session, settings=self.settings)
            asset = await service._asset(asset_id)
            asset.status = MediaAssetStatus.READY_FOR_REVIEW.value
            asset.storage_uri = storage_uri
            asset.mime_type = generated.mime_type
            asset.width = generated.width
            asset.height = generated.height
            asset.estimated_cost = Decimal(str(generated.estimated_cost))
            asset.safety_status = "PASSED_PROVIDER_AND_DETERMINISTIC_CHECKS"
            asset.completed_at = datetime.now(UTC)
            task = (
                await AppliedWorkflowRepository(session).get(asset.task_run_id)
                if asset.task_run_id
                else None
            )
            if task is not None:
                task.status = AppliedTaskStatus.COMPLETED.value
                task.result = media_to_schema(asset).model_dump(mode="json")
                task.completed_at = datetime.now(UTC)
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
                task.estimated_cost = Decimal(str(generated.estimated_cost))
            completed_attempt = await service.media.get_attempt(attempt_id)
            if completed_attempt is None:
                raise M7ResourceNotFoundError("Media generation attempt not found")
            _complete_attempt(
                completed_attempt,
                "COMPLETED",
                provider_job_id=generated.provider_job_id,
                estimated_cost=generated.estimated_cost,
            )
            await OutboxService(session).add_event(
                event_type=OutboxEventType.MEDIA_READY_FOR_REVIEW,
                aggregate_type="media_asset",
                aggregate_id=str(asset_id),
                payload={"media_asset_id": str(asset_id)},
                idempotency_key=f"media-ready:{asset_id}",
            )
            await session.commit()

    async def generate_storyboard(self, asset_id: UUID) -> None:
        attempt_id: UUID
        async with self.session_factory() as session:
            asset = await MediaService(session, settings=self.settings)._asset(asset_id)
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
            attempt = await self.media_attempt(
                session, asset_id, asset.provider, asset.model
            )
            attempt_id = attempt.attempt_id
            await session.commit()
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
        except asyncio.CancelledError:
            await self._finish_attempt(attempt_id, "CANCELLED")
            raise
        except Exception as exc:
            await self._finish_attempt(attempt_id, "FAILED", error=exc)
            raise
        async with self.session_factory() as session:
            service = MediaService(session, settings=self.settings)
            asset = await service._asset(asset_id)
            asset.status = MediaAssetStatus.READY_FOR_REVIEW.value
            asset.safety_status = "READY_FOR_HUMAN_REVIEW"
            task = (
                await AppliedWorkflowRepository(session).get(asset.task_run_id)
                if asset.task_run_id
                else None
            )
            if task is not None:
                task.status = AppliedTaskStatus.COMPLETED.value
                task.result = storyboard.model_dump(mode="json")
                task.input_tokens = completion.usage.input_tokens
                task.output_tokens = completion.usage.output_tokens
                task.estimated_cost = Decimal(str(completion.usage.estimated_cost))
                task.completed_at = datetime.now(UTC)
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
            asset.completed_at = datetime.now(UTC)
            completed_attempt = await service.media.get_attempt(attempt_id)
            if completed_attempt is None:
                raise M7ResourceNotFoundError("Media generation attempt not found")
            _complete_attempt(
                completed_attempt,
                "COMPLETED",
                estimated_cost=completion.usage.estimated_cost,
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

    async def media_attempt(
        self, session: AsyncSession, asset_id: UUID, provider: str, model: str
    ) -> MediaGenerationAttemptModel:
        repository = MediaRepository(session)
        return await repository.create_attempt(
            MediaGenerationAttemptModel(
                media_asset_id=asset_id,
                attempt_number=await repository.next_attempt_number(asset_id),
                provider=provider,
                model=model,
                status="STARTED",
            )
        )

    async def _finish_attempt(
        self, attempt_id: UUID, status: str, *, error: Exception | None = None
    ) -> None:
        async with self.session_factory() as session:
            attempt = await MediaRepository(session).get_attempt(attempt_id)
            if attempt is None:
                return
            _complete_attempt(attempt, status, error=error)
            await session.commit()

    def _image_provider(self, provider: str) -> ImageGenerationProvider:
        if provider == "mock":
            return MockImageProvider()
        if provider == "openai":
            return OpenAIImageProvider(self.settings)
        raise M7ValidationError("Image provider is not configured")


def media_to_schema(model: MediaAssetModel) -> MediaAssetRead:
    return MediaAssetRead.model_validate(model, from_attributes=True)


def _complete_attempt(
    attempt: MediaGenerationAttemptModel,
    status: str,
    *,
    error: Exception | None = None,
    provider_job_id: str | None = None,
    estimated_cost: float | None = None,
) -> None:
    now = datetime.now(UTC)
    attempt.status = status
    attempt.provider_job_id = provider_job_id
    attempt.completed_at = now
    attempt.duration_ms = _duration_ms(attempt.started_at, now)
    attempt.estimated_cost = (
        Decimal(str(estimated_cost)) if estimated_cost is not None else None
    )
    if error is not None:
        attempt.error_code = (
            error.error_code if isinstance(error, ApplicationError) else "MEDIA_ERROR"
        )
        message = (
            error.message
            if isinstance(error, ApplicationError)
            else "Media generation failed"
        )
        attempt.error_message = sanitize_text(message, max_characters=2000)


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int:
    if started_at is None:
        return 0
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import FileResponse

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.config import get_settings
from app.core.constants import MediaAssetStatus, MediaAssetType, UserRole
from app.media.service import MediaService
from app.media.storage import LocalMediaStorage
from app.core.exceptions import M7ValidationError
from app.schemas.media import (
    ImageGenerationRequest,
    MediaAssetRead,
    MediaReviewRequest,
    VideoStoryboard,
    VideoStoryboardRequest,
)
from app.service.applied_workflow_service import AppliedWorkflowService
from app.service.auth_service import AuthenticatedActor
from app.security.resource_access import ResourceAccessService

router = APIRouter(prefix="/media", tags=["Applied AI - Media"])


@router.post(
    "/images", response_model=MediaAssetRead, status_code=status.HTTP_202_ACCEPTED
)
async def create_image(
    data: ImageGenerationRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    idempotency_key: Annotated[
        str | None, Header(alias="X-Idempotency-Key", max_length=200)
    ] = None,
) -> MediaAssetRead:
    access = ResourceAccessService(session)
    if data.campaign_id is not None:
        await access.require_campaign_access(actor, data.campaign_id, write=True)
    if data.workflow_id is not None:
        await access.require_workflow_access(actor, data.workflow_id, write=True)
    return await MediaService(session).request_image(
        data, actor=actor, idempotency_key=idempotency_key
    )


@router.get("/assets", response_model=list[MediaAssetRead])
async def list_media_assets(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: MediaAssetStatus | None = None,
    campaign_id: str | None = None,
) -> list[MediaAssetRead]:
    if campaign_id is not None:
        await ResourceAccessService(session).require_campaign_access(actor, campaign_id)
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    if actor.role == UserRole.REVIEWER:
        owner_id = None
        status_filter = MediaAssetStatus.READY_FOR_REVIEW
    return await MediaService(session).list_assets(
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        status=status_filter,
        campaign_id=campaign_id,
    )


@router.get("/storyboards", response_model=list[MediaAssetRead])
async def list_storyboards(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: MediaAssetStatus | None = None,
) -> list[MediaAssetRead]:
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    if actor.role == UserRole.REVIEWER:
        owner_id = None
        status_filter = MediaAssetStatus.READY_FOR_REVIEW
    return await MediaService(session).list_assets(
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        asset_type=MediaAssetType.VIDEO_STORYBOARD,
        status=status_filter,
    )


@router.get("/assets/{asset_id}", response_model=MediaAssetRead)
async def get_media_asset(
    asset_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    await ResourceAccessService(session).require_media_access(actor, asset_id)
    return await MediaService(session).get(asset_id)


@router.get("/assets/{asset_id}/content", response_class=FileResponse)
async def get_media_content(
    asset_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> FileResponse:
    await ResourceAccessService(session).require_media_access(actor, asset_id)
    asset = await MediaService(session).get(asset_id)
    if asset.storage_uri is None or asset.mime_type is None:
        raise M7ValidationError("Media content is not ready")
    path = LocalMediaStorage(get_settings().media_storage_root).resolve(
        asset.storage_uri
    )
    return FileResponse(path, media_type=asset.mime_type)


@router.post("/assets/{asset_id}/approve", response_model=MediaAssetRead)
async def approve_media_asset(
    asset_id: UUID,
    data: MediaReviewRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    await ResourceAccessService(session).require_media_access(
        actor, asset_id, review=True
    )
    return await MediaService(session).review(
        asset_id, data.model_copy(update={"decision": "APPROVE"}), actor=actor
    )


@router.post("/assets/{asset_id}/reject", response_model=MediaAssetRead)
async def reject_media_asset(
    asset_id: UUID,
    data: MediaReviewRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    await ResourceAccessService(session).require_media_access(
        actor, asset_id, review=True
    )
    return await MediaService(session).review(
        asset_id, data.model_copy(update={"decision": "REJECT"}), actor=actor
    )


@router.post(
    "/video-storyboards",
    response_model=MediaAssetRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_video_storyboard(
    data: VideoStoryboardRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    if data.campaign_id is not None:
        await ResourceAccessService(session).require_campaign_access(
            actor, data.campaign_id, write=True
        )
    return await MediaService(session).request_storyboard(data, actor=actor)


@router.get("/video-storyboards/{asset_id}", response_model=VideoStoryboard)
async def get_video_storyboard(
    asset_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> VideoStoryboard:
    await ResourceAccessService(session).require_media_access(actor, asset_id)
    asset = await MediaService(session).get(asset_id)
    if asset.task_run_id is None:
        raise M7ValidationError("Storyboard task is missing")
    task = await AppliedWorkflowService(session).get(asset.task_run_id)
    if task.result is None:
        raise M7ValidationError("Storyboard is not ready")
    return VideoStoryboard.model_validate(task.result)

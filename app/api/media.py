from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.media.service import MediaService
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

router = APIRouter(prefix="/media", tags=["Applied AI - Media"])


@router.post(
    "/images", response_model=MediaAssetRead, status_code=status.HTTP_202_ACCEPTED
)
async def create_image(
    data: ImageGenerationRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    return await MediaService(session).request_image(data, actor=actor)


@router.get("/assets/{asset_id}", response_model=MediaAssetRead)
async def get_media_asset(
    asset_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
    return await MediaService(session).get(asset_id)


@router.post("/assets/{asset_id}/approve", response_model=MediaAssetRead)
async def approve_media_asset(
    asset_id: UUID,
    data: MediaReviewRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> MediaAssetRead:
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
    return await MediaService(session).request_storyboard(data, actor=actor)


@router.get("/video-storyboards/{asset_id}", response_model=VideoStoryboard)
async def get_video_storyboard(
    asset_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> VideoStoryboard:
    asset = await MediaService(session).get(asset_id)
    if asset.task_run_id is None:
        raise M7ValidationError("Storyboard task is missing")
    task = await AppliedWorkflowService(session).get(asset.task_run_id)
    if task.result is None:
        raise M7ValidationError("Storyboard is not ready")
    return VideoStoryboard.model_validate(task.result)

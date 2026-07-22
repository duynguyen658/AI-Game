from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.config import get_settings
from app.core.constants import AppliedTaskStatus, AppliedWorkflowType, UserRole
from app.core.exceptions import M7ValidationError
from app.security.resource_access import ResourceAccessService
from app.schemas.applied_workflow import AppliedTaskRead
from app.schemas.document_processing import DocumentProcessingResult
from app.service.applied_workflow_service import AppliedWorkflowService
from app.service.auth_service import AuthenticatedActor
from app.service.document_processing_service import DocumentProcessingService

router = APIRouter(prefix="/document-processing/tasks", tags=["Applied AI - Documents"])


@router.post("", response_model=AppliedTaskRead, status_code=status.HTTP_202_ACCEPTED)
async def create_document_processing_task(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    file: Annotated[UploadFile, File()],
) -> AppliedTaskRead:
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise M7ValidationError("Document exceeds the configured size limit")
    return await DocumentProcessingService(session).request(
        content,
        file.filename or "upload.txt",
        file.content_type or "application/octet-stream",
        actor_id=actor.actor_id,
    )


@router.get("", response_model=list[AppliedTaskRead])
async def list_document_processing_tasks(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: AppliedTaskStatus | None = None,
) -> list[AppliedTaskRead]:
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    return await AppliedWorkflowService(session).list(
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        workflow_type=AppliedWorkflowType.DOCUMENT_PROCESSING,
        status=status_filter,
    )


@router.get("/{task_run_id}", response_model=AppliedTaskRead)
async def get_document_processing_task(
    task_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AppliedTaskRead:
    await ResourceAccessService(session).require_task_access(actor, task_run_id)
    return await AppliedWorkflowService(session).get(task_run_id)


@router.get("/{task_run_id}/result", response_model=DocumentProcessingResult)
async def get_document_processing_result(
    task_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> DocumentProcessingResult:
    await ResourceAccessService(session).require_task_access(actor, task_run_id)
    task = await AppliedWorkflowService(session).get(task_run_id)
    if task.result is None:
        raise M7ValidationError("Document processing result is not ready")
    return DocumentProcessingResult.model_validate(task.result)

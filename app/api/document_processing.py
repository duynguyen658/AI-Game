from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.config import get_settings
from app.core.exceptions import M7ValidationError
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


@router.get("/{task_run_id}", response_model=AppliedTaskRead)
async def get_document_processing_task(
    task_run_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AppliedTaskRead:
    return await AppliedWorkflowService(session).get(task_run_id)


@router.get("/{task_run_id}/result", response_model=DocumentProcessingResult)
async def get_document_processing_result(
    task_run_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> DocumentProcessingResult:
    task = await AppliedWorkflowService(session).get(task_run_id)
    if task.result is None:
        raise M7ValidationError("Document processing result is not ready")
    return DocumentProcessingResult.model_validate(task.result)

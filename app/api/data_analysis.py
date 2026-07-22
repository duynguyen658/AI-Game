from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.config import get_settings
from app.core.constants import AppliedTaskStatus, AppliedWorkflowType, UserRole
from app.core.exceptions import M7ValidationError
from app.security.resource_access import ResourceAccessService
from app.schemas.applied_workflow import AppliedTaskRead
from app.schemas.data_analysis import DataAnalysisReport
from app.service.applied_workflow_service import AppliedWorkflowService
from app.service.auth_service import AuthenticatedActor
from app.service.data_analysis_service import DataAnalysisService

router = APIRouter(prefix="/data-analysis/tasks", tags=["Applied AI - Data Analysis"])


@router.post("", response_model=AppliedTaskRead, status_code=status.HTTP_202_ACCEPTED)
async def create_data_analysis_task(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    file: Annotated[UploadFile, File()],
) -> AppliedTaskRead:
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise M7ValidationError("CSV exceeds the configured size limit")
    return await DataAnalysisService(session).request(
        content, file.filename or "upload.csv", actor_id=actor.actor_id
    )


@router.get("", response_model=list[AppliedTaskRead])
async def list_data_analysis_tasks(
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
        workflow_type=AppliedWorkflowType.DATA_ANALYSIS,
        status=status_filter,
    )


@router.get("/{task_run_id}", response_model=AppliedTaskRead)
async def get_data_analysis_task(
    task_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AppliedTaskRead:
    await ResourceAccessService(session).require_task_access(actor, task_run_id)
    return await AppliedWorkflowService(session).get(task_run_id)


@router.get("/{task_run_id}/report", response_model=DataAnalysisReport)
async def get_data_analysis_report(
    task_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> DataAnalysisReport:
    await ResourceAccessService(session).require_task_access(actor, task_run_id)
    task = await AppliedWorkflowService(session).get(task_run_id)
    if task.result is None:
        raise M7ValidationError("Data analysis report is not ready")
    return DataAnalysisReport.model_validate(task.result)

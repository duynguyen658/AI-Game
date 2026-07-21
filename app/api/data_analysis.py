from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.config import get_settings
from app.core.exceptions import M7ValidationError
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


@router.get("/{task_run_id}", response_model=AppliedTaskRead)
async def get_data_analysis_task(
    task_run_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AppliedTaskRead:
    return await AppliedWorkflowService(session).get(task_run_id)


@router.get("/{task_run_id}/report", response_model=DataAnalysisReport)
async def get_data_analysis_report(
    task_run_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> DataAnalysisReport:
    task = await AppliedWorkflowService(session).get(task_run_id)
    if task.result is None:
        raise M7ValidationError("Data analysis report is not ready")
    return DataAnalysisReport.model_validate(task.result)

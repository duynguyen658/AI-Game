from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDependency, get_llm_client
from app.llm.base import LLMClient
from app.schemas.workflow_run import WorkflowRun
from app.service.workflow_service import WorkflowService
from app.workflows.campaign_workflow import CampaignWorkflow

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("/campaigns/{campaign_id}", response_model=WorkflowRun, status_code=201)
async def create_workflow(
    campaign_id: str,
    session: SessionDependency,
) -> WorkflowRun:
    return await WorkflowService(session).create_workflow(campaign_id)


@router.get("/{workflow_id}", response_model=WorkflowRun)
async def get_workflow(
    workflow_id: UUID,
    session: SessionDependency,
) -> WorkflowRun:
    return await WorkflowService(session).get_workflow(workflow_id)


@router.post("/{workflow_id}/run", response_model=WorkflowRun)
async def run_workflow(
    workflow_id: UUID,
    session: SessionDependency,
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
) -> WorkflowRun:
    return await CampaignWorkflow(session, llm_client).run_to_pending_approval(
        workflow_id
    )

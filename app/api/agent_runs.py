from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.schemas.agent_run import AgentRunRead
from app.schemas.tool_call import ToolCallRead
from app.service.agent_run_service import AgentRunService
from app.service.auth_service import AuthenticatedActor, AuthService
from app.database.models import AgentRunModel
from app.core.exceptions import AgentRunNotFoundError
from app.security.resource_access import ResourceAccessService

router = APIRouter(tags=["Agent Runs"])


@router.get("/agent-runs", response_model=list[AgentRunRead])
async def list_agent_runs(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    AuthService().require_operator(actor)
    return await AgentRunService(session).list_runs(limit=limit, offset=offset)


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(
    agent_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AgentRunRead:
    AuthService().require_agent_run_read(actor)
    run = await session.get(AgentRunModel, agent_run_id)
    if run is None:
        raise AgentRunNotFoundError("Agent run not found")
    await ResourceAccessService(session).require_workflow_access(actor, run.workflow_id)
    return await AgentRunService(session).get_run(agent_run_id)


@router.get("/agent-runs/{agent_run_id}/tool-calls", response_model=list[ToolCallRead])
async def list_agent_tool_calls(
    agent_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[ToolCallRead]:
    AuthService().require_operator(actor)
    return await AgentRunService(session).list_tool_calls(agent_run_id)


@router.get("/workflows/{workflow_id}/agent-runs", response_model=list[AgentRunRead])
async def list_workflow_agent_runs(
    workflow_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    AuthService().require_agent_run_read(actor)
    await ResourceAccessService(session).require_workflow_access(actor, workflow_id)
    return await AgentRunService(session).list_workflow_runs(
        workflow_id, limit=limit, offset=offset
    )


@router.get("/campaigns/{campaign_id}/agent-runs", response_model=list[AgentRunRead])
async def list_campaign_agent_runs(
    campaign_id: str,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    AuthService().require_agent_run_read(actor)
    await ResourceAccessService(session).require_campaign_access(actor, campaign_id)
    return await AgentRunService(session).list_campaign_runs(
        campaign_id, limit=limit, offset=offset
    )

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.schemas.agent_run import AgentRunRead
from app.schemas.tool_call import ToolCallRead
from app.service.agent_run_service import AgentRunService

router = APIRouter(tags=["Agent Runs"])


@router.get("/agent-runs", response_model=list[AgentRunRead])
async def list_agent_runs(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    return await AgentRunService(session).list_runs(limit=limit, offset=offset)


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(agent_run_id: UUID, session: SessionDependency) -> AgentRunRead:
    return await AgentRunService(session).get_run(agent_run_id)


@router.get("/agent-runs/{agent_run_id}/tool-calls", response_model=list[ToolCallRead])
async def list_agent_tool_calls(
    agent_run_id: UUID, session: SessionDependency
) -> list[ToolCallRead]:
    return await AgentRunService(session).list_tool_calls(agent_run_id)


@router.get("/workflows/{workflow_id}/agent-runs", response_model=list[AgentRunRead])
async def list_workflow_agent_runs(
    workflow_id: UUID,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    return await AgentRunService(session).list_runs(
        workflow_id=workflow_id, limit=limit, offset=offset
    )


@router.get("/campaigns/{campaign_id}/agent-runs", response_model=list[AgentRunRead])
async def list_campaign_agent_runs(
    campaign_id: str,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunRead]:
    return await AgentRunService(session).list_runs(
        campaign_id=campaign_id, limit=limit, offset=offset
    )

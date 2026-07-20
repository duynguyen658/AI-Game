from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.definitions import ToolDefinition
from app.service.agent_query_service import AgentReadQueryService


class WorkflowToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str
    workflow_id: UUID


class CampaignReadTools:
    def __init__(self, queries: AgentReadQueryService) -> None:
        self.queries = queries

    async def get_previous_quality_review(
        self, _: CampaignContext, payload: BaseModel
    ) -> object:
        request = WorkflowToolInput.model_validate(payload)
        return await self.queries.get_previous_quality_review(
            campaign_id=request.campaign_id,
            workflow_id=request.workflow_id,
        )

    async def get_previous_revision(
        self, _: CampaignContext, payload: BaseModel
    ) -> object:
        request = WorkflowToolInput.model_validate(payload)
        return await self.queries.get_previous_revision(
            campaign_id=request.campaign_id,
            workflow_id=request.workflow_id,
        )

    async def get_previous_workflow_summary(
        self, _: CampaignContext, payload: BaseModel
    ) -> object:
        request = WorkflowToolInput.model_validate(payload)
        return await self.queries.get_previous_workflow_summary(
            campaign_id=request.campaign_id,
            workflow_id=request.workflow_id,
        )


def campaign_tool_definitions(
    query_service: AgentReadQueryService,
) -> list[ToolDefinition]:
    tools = CampaignReadTools(query_service)
    return [
        ToolDefinition(
            name="get_previous_quality_review",
            description="Read the latest persisted quality feedback for this workflow campaign.",
            input_model=WorkflowToolInput,
            handler=tools.get_previous_quality_review,
        ),
        ToolDefinition(
            name="get_previous_revision",
            description="Read bounded parent revision metadata and prior campaign artifacts.",
            input_model=WorkflowToolInput,
            handler=tools.get_previous_revision,
        ),
        ToolDefinition(
            name="get_previous_workflow_summary",
            description="Read a bounded summary of the parent workflow when one exists.",
            input_model=WorkflowToolInput,
            handler=tools.get_previous_workflow_summary,
        ),
    ]

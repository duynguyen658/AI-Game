from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.definitions import ToolDefinition


class CampaignToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str


class WorkflowToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str
    workflow_id: UUID


async def get_campaign(context: CampaignContext, _: BaseModel) -> object:
    return {
        "campaign_id": context.campaign_id,
        "game_name": context.game_name,
        "genre": context.genre,
        "target_audience": context.target_audience,
        "market": context.market,
        "platforms": [item.value for item in context.platforms],
        "campaign_objective": context.campaign_objective,
        "tone": context.tone,
        "launch_date": context.launch_date.isoformat(),
        "promotion": context.promotion,
        "raw_brief": context.raw_brief,
    }


async def get_workflow(context: CampaignContext, _: BaseModel) -> object:
    return {
        "workflow_id": str(context.workflow_id),
        "campaign_id": context.campaign_id,
        "status": context.current_workflow_status.value,
        "retry_count": context.retry_count,
        "revision_number": context.revision_number,
        "parent_workflow_id": str(context.parent_workflow_id)
        if context.parent_workflow_id
        else None,
    }


async def get_brief_analysis(context: CampaignContext, _: BaseModel) -> object:
    return context.brief_analysis or {"available": False}


async def get_generated_content(context: CampaignContext, _: BaseModel) -> object:
    return context.generated_content or {"available": False}


async def get_previous_quality_review(context: CampaignContext, _: BaseModel) -> object:
    return context.quality_review or {"available": False}


async def get_previous_revision(context: CampaignContext, _: BaseModel) -> object:
    return {
        "revision_number": context.revision_number,
        "parent_workflow_id": str(context.parent_workflow_id)
        if context.parent_workflow_id
        else None,
        "generated_content": context.generated_content,
        "quality_review": context.quality_review,
    }


async def get_previous_workflow_summary(
    context: CampaignContext, _: BaseModel
) -> object:
    return {
        "revision_number": context.revision_number,
        "parent_workflow_id": str(context.parent_workflow_id)
        if context.parent_workflow_id
        else None,
        "previous_review": context.quality_review,
    }


def campaign_tool_definitions() -> list[ToolDefinition]:
    workflow_tools = {
        "get_workflow": get_workflow,
        "get_brief_analysis": get_brief_analysis,
        "get_generated_content": get_generated_content,
        "get_previous_quality_review": get_previous_quality_review,
        "get_previous_revision": get_previous_revision,
        "get_previous_workflow_summary": get_previous_workflow_summary,
    }
    definitions = [
        ToolDefinition(
            name="get_campaign",
            description="Read the bounded campaign brief and targeting fields.",
            input_model=CampaignToolInput,
            handler=get_campaign,
        )
    ]
    definitions.extend(
        ToolDefinition(
            name=name,
            description=f"Read bounded {name.removeprefix('get_').replace('_', ' ')} data.",
            input_model=WorkflowToolInput,
            handler=handler,
        )
        for name, handler in workflow_tools.items()
    )
    return definitions

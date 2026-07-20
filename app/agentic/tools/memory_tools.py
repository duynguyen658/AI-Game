from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.definitions import ToolDefinition
from app.service.memory_service import MemoryService


class MemoryToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(min_length=3, max_length=100)
    workflow_id: UUID
    limit: int = Field(default=10, ge=1, le=20)


def memory_tool_definitions(service: MemoryService) -> list[ToolDefinition]:
    async def recent(_: CampaignContext, payload: BaseModel) -> object:
        payload = MemoryToolInput.model_validate(payload)
        entries = await service.recent_campaign(
            payload.campaign_id, limit=payload.limit
        )
        return [entry.model_dump(mode="json") for entry in entries]

    async def failures(_: CampaignContext, payload: BaseModel) -> object:
        payload = MemoryToolInput.model_validate(payload)
        entries = await service.previous_failures(
            payload.campaign_id, limit=payload.limit
        )
        return [entry.model_dump(mode="json") for entry in entries]

    async def feedback(_: CampaignContext, payload: BaseModel) -> object:
        payload = MemoryToolInput.model_validate(payload)
        entries = await service.previous_review_feedback(
            payload.campaign_id, limit=payload.limit
        )
        return [entry.model_dump(mode="json") for entry in entries]

    async def action_results(_: CampaignContext, payload: BaseModel) -> object:
        payload = MemoryToolInput.model_validate(payload)
        entries = await service.previous_action_results(
            payload.campaign_id, limit=payload.limit
        )
        return [entry.model_dump(mode="json") for entry in entries]

    return [
        ToolDefinition(
            name="get_recent_campaign_memories",
            description="Read bounded recent structured campaign memory.",
            input_model=MemoryToolInput,
            handler=recent,
        ),
        ToolDefinition(
            name="get_previous_failures",
            description="Read bounded previous controlled-action failures.",
            input_model=MemoryToolInput,
            handler=failures,
        ),
        ToolDefinition(
            name="get_previous_review_feedback",
            description="Read bounded previous review feedback.",
            input_model=MemoryToolInput,
            handler=feedback,
        ),
        ToolDefinition(
            name="get_previous_action_results",
            description="Read bounded previous controlled-action results.",
            input_model=MemoryToolInput,
            handler=action_results,
        ),
    ]

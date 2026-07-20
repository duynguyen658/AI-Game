from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.agentic.state.campaign_context import CampaignContext

ToolHandler = Callable[[CampaignContext, BaseModel], Awaitable[object]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    read_only: bool = True

    def provider_schema(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema(),
        }

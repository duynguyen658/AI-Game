from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import AgentName, CampaignStatus, PolicyDecision, UserRole


class ActionExecutionGuard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str
    workflow_id: UUID
    expected_campaign_status: CampaignStatus
    expected_campaign_version: int
    expected_workflow_status: CampaignStatus
    expected_revision_number: int


InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)
ActionHandler = Callable[[InputT, ActionExecutionGuard], Awaitable[OutputT]]


@dataclass(frozen=True)
class ActionDefinition(Generic[InputT, OutputT]):
    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    default_policy: PolicyDecision
    reversible: bool
    allowed_agents: frozenset[AgentName]
    handler: ActionHandler[InputT, OutputT]
    required_role: UserRole | None = None
    allowed_campaign_statuses: frozenset[CampaignStatus] = frozenset()
    allowed_workflow_statuses: frozenset[CampaignStatus] = frozenset()
    approval_ttl_seconds: int | None = None

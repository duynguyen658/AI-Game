from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.definitions import ActionDefinition
from app.agentic.actions.registry import ActionRegistry
from app.agentic.policies.engine import PolicyEngine
from app.core.constants import AgentName, CampaignStatus
from app.core.exceptions import (
    ActionNotFoundError,
    AgentContextError,
    AgentRunNotFoundError,
)
from app.repositories.action_request_repository import ActionRequestRepository
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.action_request import AgentActionProposal
from app.schemas.policy_decision import (
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


class PolicyService:
    def __init__(
        self,
        session: AsyncSession,
        registry: ActionRegistry,
        *,
        engine: PolicyEngine | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.engine = engine or PolicyEngine()
        self.runs = AgentRunRepository(session)
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)
        self.requests = ActionRequestRepository(session)

    async def evaluate(
        self,
        *,
        agent_run_id: UUID,
        agent_name: AgentName,
        proposal: AgentActionProposal,
    ) -> tuple[
        PolicyEvaluationResult, ActionDefinition | None, PolicyEvaluationContext
    ]:
        run = await self.runs.get_by_id(agent_run_id)
        if run is None:
            await self.session.rollback()
            raise AgentRunNotFoundError("Agent run not found")
        campaign = await self.campaigns.get_by_id(run.campaign_id)
        workflow = await self.workflows.get_by_id(run.workflow_id)
        if campaign is None or workflow is None:
            await self.session.rollback()
            raise AgentContextError("Action proposal scope is unavailable")
        if run.agent_name != agent_name.value:
            await self.session.rollback()
            raise AgentContextError("Action Agent does not match Agent run")
        existing = await self.requests.list(
            workflow_id=run.workflow_id, limit=100, offset=0
        )
        context = PolicyEvaluationContext(
            agent_run_id=agent_run_id,
            workflow_id=run.workflow_id,
            campaign_id=run.campaign_id,
            agent_name=agent_name,
            action_name=proposal.action_name,
            arguments=proposal.arguments,
            campaign_status=CampaignStatus(campaign.status),
            workflow_status=CampaignStatus(workflow.status),
            revision_number=workflow.revision_number,
            previous_action_count=len(existing),
        )
        definition = self._definition(proposal.action_name)
        result = self.engine.evaluate(context, definition)
        await self.session.commit()
        return result, definition, context

    def _definition(self, action_name: str) -> ActionDefinition | None:
        try:
            return self.registry.get(action_name)
        except ActionNotFoundError:
            return None

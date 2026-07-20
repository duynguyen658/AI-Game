from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agentic.actions.definitions import ActionDefinition
from app.agentic.actions.registry import ActionRegistry
from app.agentic.policies.engine import PolicyEngine
from app.core.constants import (
    AgentName,
    CampaignStatus,
    PolicyDecision,
    UserRole,
)
from app.core.exceptions import ActionNotAllowedError, ActionNotFoundError
from app.schemas.policy_decision import PolicyEvaluationContext


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    note: str = Field(min_length=1, max_length=100)


class Output(BaseModel):
    message: str


async def handler(_: Input) -> Output:
    return Output(message="done")


def definition(
    *,
    name: str = "create_internal_recommendation",
    policy: PolicyDecision = PolicyDecision.SAFE,
    agents: frozenset[AgentName] = frozenset({AgentName.BRIEF_ANALYST}),
    statuses: frozenset[CampaignStatus] = frozenset(),
) -> ActionDefinition[Input, Output]:
    return ActionDefinition(
        name=name,
        description="Internal test action",
        input_model=Input,
        output_model=Output,
        default_policy=policy,
        reversible=True,
        allowed_agents=agents,
        handler=handler,
        required_role=(
            UserRole.MANAGER if policy == PolicyDecision.APPROVAL_REQUIRED else None
        ),
        allowed_campaign_statuses=statuses,
        approval_ttl_seconds=(
            3600 if policy == PolicyDecision.APPROVAL_REQUIRED else None
        ),
    )


def context(
    *,
    action_name: str = "create_internal_recommendation",
    arguments: dict | None = None,
    agent_name: AgentName = AgentName.BRIEF_ANALYST,
    status: CampaignStatus = CampaignStatus.ANALYZING,
) -> PolicyEvaluationContext:
    return PolicyEvaluationContext(
        agent_run_id=uuid4(),
        workflow_id=uuid4(),
        campaign_id="CL-POLICY",
        agent_name=agent_name,
        action_name=action_name,
        arguments=arguments or {"campaign_id": "CL-POLICY", "note": "safe"},
        campaign_status=status,
        workflow_status=status,
    )


def test_policy_classifies_safe_and_approval_required() -> None:
    engine = PolicyEngine()
    safe = engine.evaluate(context(), definition())
    approval = engine.evaluate(
        context(action_name="add_manual_review_note"),
        definition(
            name="add_manual_review_note",
            policy=PolicyDecision.APPROVAL_REQUIRED,
        ),
    )

    assert safe.decision == PolicyDecision.SAFE
    assert safe.reason_code == "SAFE_INTERNAL_ACTION"
    assert approval.decision == PolicyDecision.APPROVAL_REQUIRED
    assert approval.required_role == UserRole.MANAGER
    assert approval.expires_in_seconds == 3600


@pytest.mark.parametrize(
    ("action_name", "reason_code"),
    [
        ("publish_campaign", "FORBIDDEN_ACTION"),
        ("Publish-Campaign", "FORBIDDEN_ACTION"),
        ("execute command", "FORBIDDEN_ACTION"),
        ("unknown_action", "UNKNOWN_ACTION"),
    ],
)
def test_policy_default_denies_unknown_forbidden_and_aliases(
    action_name: str, reason_code: str
) -> None:
    result = PolicyEngine().evaluate(context(action_name=action_name), None)
    assert result.decision == PolicyDecision.FORBIDDEN
    assert result.reason_code == reason_code


def test_policy_denies_nested_action_invalid_input_agent_and_state() -> None:
    engine = PolicyEngine()
    registered = definition(statuses=frozenset({CampaignStatus.REVIEWING}))

    nested = engine.evaluate(
        context(
            arguments={
                "campaign_id": "CL-POLICY",
                "note": "safe",
                "action": "publish_campaign",
            }
        ),
        registered,
    )
    invalid = engine.evaluate(
        context(arguments={"campaign_id": "CL-POLICY"}), registered
    )
    wrong_agent = engine.evaluate(
        context(agent_name=AgentName.CONTENT_GENERATOR), registered
    )
    wrong_state = engine.evaluate(context(), registered)

    assert nested.reason_code == "DANGEROUS_ARGUMENTS"
    assert invalid.reason_code == "INVALID_ARGUMENTS"
    assert wrong_agent.reason_code == "AGENT_NOT_ALLOWED"
    assert wrong_state.reason_code == "CAMPAIGN_STATE_NOT_ALLOWED"

    base_context = context()
    wrong_scope_context = base_context.model_copy(
        update={
            "arguments": {
                **base_context.arguments,
                "campaign_id": "CL-OTHER",
            }
        }
    )
    wrong_scope = engine.evaluate(wrong_scope_context, registered)
    assert wrong_scope.decision == PolicyDecision.FORBIDDEN
    assert wrong_scope.reason_code == "ACTION_SCOPE_MISMATCH"


def test_registry_rejects_duplicate_unknown_and_disallowed_agent() -> None:
    registered = definition()
    registry = ActionRegistry([registered])

    assert registry.get(registered.name) is registered
    assert registry.list_for_agent(AgentName.BRIEF_ANALYST) == (registered,)
    with pytest.raises(ValueError, match="Duplicate"):
        ActionRegistry([registered, registered])
    with pytest.raises(ActionNotFoundError):
        registry.get("missing")
    with pytest.raises(ActionNotAllowedError):
        registry.get_for_agent(AgentName.CONTENT_REVIEWER, registered.name)

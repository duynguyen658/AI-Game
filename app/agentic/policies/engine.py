from __future__ import annotations

from pydantic import ValidationError

from app.agentic.actions.definitions import ActionDefinition
from app.agentic.policies.rules import contains_nested_danger, is_forbidden_alias
from app.core.constants import PolicyDecision
from app.schemas.policy_decision import (
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


class PolicyEngine:
    def evaluate(
        self,
        context: PolicyEvaluationContext,
        definition: ActionDefinition | None,
    ) -> PolicyEvaluationResult:
        if is_forbidden_alias(context.action_name):
            return self._deny("FORBIDDEN_ACTION", "Action is permanently forbidden")
        if definition is None or context.action_name != definition.name:
            return self._deny("UNKNOWN_ACTION", "Action is not explicitly registered")
        if context.agent_name not in definition.allowed_agents:
            return self._deny(
                "AGENT_NOT_ALLOWED", "Agent is not allowed to propose action"
            )
        if contains_nested_danger(context.arguments):
            return self._deny(
                "DANGEROUS_ARGUMENTS", "Action arguments contain a forbidden operation"
            )
        try:
            validated_arguments = definition.input_model.model_validate(
                context.arguments
            )
        except ValidationError:
            return self._deny("INVALID_ARGUMENTS", "Action arguments are invalid")
        if (
            getattr(validated_arguments, "campaign_id", context.campaign_id)
            != context.campaign_id
            or getattr(validated_arguments, "workflow_id", context.workflow_id)
            != context.workflow_id
            or getattr(validated_arguments, "revision_number", context.revision_number)
            != context.revision_number
        ):
            return self._deny(
                "ACTION_SCOPE_MISMATCH",
                "Action scope does not match the active Agent run",
            )
        if (
            definition.allowed_campaign_statuses
            and context.campaign_status not in definition.allowed_campaign_statuses
        ):
            return self._deny(
                "CAMPAIGN_STATE_NOT_ALLOWED",
                "Campaign state does not allow this action",
            )
        if (
            definition.allowed_workflow_statuses
            and context.workflow_status not in definition.allowed_workflow_statuses
        ):
            return self._deny(
                "WORKFLOW_STATE_NOT_ALLOWED",
                "Workflow state does not allow this action",
            )
        if definition.default_policy == PolicyDecision.SAFE:
            return PolicyEvaluationResult(
                decision=PolicyDecision.SAFE,
                reason_code="SAFE_INTERNAL_ACTION",
                reason="Action is internal, bounded, reversible, and allowlisted",
                reversible=definition.reversible,
            )
        if definition.default_policy == PolicyDecision.APPROVAL_REQUIRED:
            return PolicyEvaluationResult(
                decision=PolicyDecision.APPROVAL_REQUIRED,
                reason_code="HUMAN_APPROVAL_REQUIRED",
                reason="Action requires an authorized human decision",
                required_role=definition.required_role,
                expires_in_seconds=definition.approval_ttl_seconds,
                reversible=definition.reversible,
            )
        return self._deny("DEFAULT_DENY", "Action has no executable policy")

    def _deny(self, code: str, reason: str) -> PolicyEvaluationResult:
        return PolicyEvaluationResult(
            decision=PolicyDecision.FORBIDDEN,
            reason_code=code,
            reason=reason,
            reversible=False,
        )

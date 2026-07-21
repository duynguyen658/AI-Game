class ApplicationError(Exception):
    error_code = "APPLICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CampaignValidationError(ApplicationError):
    error_code = "CAMPAIGN_VALIDATION_ERROR"


class CampaignNotFoundError(ApplicationError):
    error_code = "CAMPAIGN_NOT_FOUND"


class CampaignAlreadyExistsError(ApplicationError):
    error_code = "CAMPAIGN_ALREADY_EXISTS"


class AuthorizationError(ApplicationError):
    error_code = "AUTHORIZATION_ERROR"


class AuthenticationError(ApplicationError):
    error_code = "AUTHENTICATION_ERROR"


class LLMResponseError(ApplicationError):
    error_code = "LLM_RESPONSE_ERROR"


class LLMProviderError(ApplicationError):
    error_code = "LLM_PROVIDER_ERROR"


class LLMProviderUnavailableError(LLMProviderError):
    error_code = "LLM_PROVIDER_UNAVAILABLE"


class LLMRateLimitError(LLMProviderError):
    error_code = "LLM_RATE_LIMITED"


class LLMTimeoutError(ApplicationError):
    error_code = "LLM_TIMEOUT"


class WorkflowLimitError(ApplicationError):
    error_code = "WORKFLOW_LIMIT_ERROR"


class WorkflowExecutionError(ApplicationError):
    error_code = "WORKFLOW_EXECUTION_ERROR"


class WorkflowNotFoundError(ApplicationError):
    error_code = "WORKFLOW_NOT_FOUND"


class WorkflowAlreadyActiveError(ApplicationError):
    error_code = "WORKFLOW_ALREADY_ACTIVE"


class WorkflowCreationNotAllowedError(ApplicationError):
    error_code = "WORKFLOW_CREATION_NOT_ALLOWED"


class InvalidStateTransitionError(ApplicationError):
    error_code = "INVALID_STATE_TRANSITION"


class ApprovalNotAllowedError(ApplicationError):
    error_code = "APPROVAL_NOT_ALLOWED"


class ApprovalAlreadyDecidedError(ApplicationError):
    error_code = "APPROVAL_ALREADY_DECIDED"


class VersionConflictError(ApplicationError):
    error_code = "VERSION_CONFLICT"


class DatabaseUnavailableError(ApplicationError):
    error_code = "DATABASE_UNAVAILABLE"


class PersistenceError(ApplicationError):
    error_code = "PERSISTENCE_ERROR"


class AgentRunNotFoundError(ApplicationError):
    error_code = "AGENT_RUN_NOT_FOUND"


class AgentRunAlreadyActiveError(ApplicationError):
    error_code = "AGENT_RUN_ALREADY_ACTIVE"


class AgentExecutionError(ApplicationError):
    error_code = "AGENT_EXECUTION_ERROR"


class AgentExecutionCancelledError(AgentExecutionError):
    error_code = "AGENT_EXECUTION_CANCELLED"


class AgentOutputValidationError(AgentExecutionError):
    error_code = "AGENT_OUTPUT_VALIDATION_ERROR"


class AgentIterationLimitError(AgentExecutionError):
    error_code = "AGENT_ITERATION_LIMIT"


class AgentLLMCallLimitError(AgentExecutionError):
    error_code = "AGENT_LLM_CALL_LIMIT"


class AgentToolCallLimitError(AgentExecutionError):
    error_code = "AGENT_TOOL_CALL_LIMIT"


class AgentTimeoutError(AgentExecutionError):
    error_code = "AGENT_TIMEOUT"


class ToolNotFoundError(AgentExecutionError):
    error_code = "TOOL_NOT_FOUND"


class ToolNotAllowedError(AgentExecutionError):
    error_code = "TOOL_NOT_ALLOWED"


class ToolInputValidationError(AgentExecutionError):
    error_code = "TOOL_INPUT_VALIDATION_ERROR"


class ToolExecutionError(AgentExecutionError):
    error_code = "TOOL_EXECUTION_ERROR"


class ToolTimeoutError(ToolExecutionError):
    error_code = "TOOL_TIMEOUT"


class ToolCancelledError(ToolExecutionError):
    error_code = "TOOL_CANCELLED"


class InvalidAgentRunTransitionError(AgentExecutionError):
    error_code = "INVALID_AGENT_RUN_TRANSITION"


class InvalidToolCallTransitionError(AgentExecutionError):
    error_code = "INVALID_TOOL_CALL_TRANSITION"


class AgentContextError(AgentExecutionError):
    error_code = "AGENT_CONTEXT_ERROR"


class AgentActionProposalLimitError(AgentExecutionError):
    error_code = "AGENT_ACTION_PROPOSAL_LIMIT"


class ActionRequestNotFoundError(ApplicationError):
    error_code = "ACTION_REQUEST_NOT_FOUND"


class ActionNotFoundError(ApplicationError):
    error_code = "ACTION_NOT_FOUND"


class ActionNotAllowedError(ApplicationError):
    error_code = "ACTION_NOT_ALLOWED"


class ActionApprovalRequiredError(ApplicationError):
    error_code = "ACTION_APPROVAL_REQUIRED"


class ActionAlreadyDecidedError(ApplicationError):
    error_code = "ACTION_ALREADY_DECIDED"


class ActionExpiredError(ApplicationError):
    error_code = "ACTION_EXPIRED"


class ActionVersionConflictError(ApplicationError):
    error_code = "ACTION_VERSION_CONFLICT"


class ActionExecutionConflictError(ApplicationError):
    error_code = "ACTION_EXECUTION_CONFLICT"


class ActionPolicyReevaluationDeniedError(ApplicationError):
    error_code = "POLICY_REEVALUATION_DENIED"


class ActionPolicyApprovalRequiredError(ApplicationError):
    error_code = "POLICY_REEVALUATION_APPROVAL_REQUIRED"


class ActionStateChangedError(ApplicationError):
    error_code = "ACTION_STATE_CHANGED"


class ActionScopeConflictError(ApplicationError):
    error_code = "ACTION_SCOPE_CONFLICT"


class ControlledActionExecutionError(ApplicationError):
    error_code = "ACTION_EXECUTION_ERROR"


class PolicyDeniedError(ApplicationError):
    error_code = "POLICY_DENIED"


class MemoryEntryNotFoundError(ApplicationError):
    error_code = "MEMORY_ENTRY_NOT_FOUND"


class JobNotFoundError(ApplicationError):
    error_code = "JOB_NOT_FOUND"


class JobConflictError(ApplicationError):
    error_code = "JOB_CONFLICT"


class JobLeaseLostError(ApplicationError):
    error_code = "JOB_LEASE_LOST"


class JobPayloadError(ApplicationError):
    error_code = "JOB_PAYLOAD_INVALID"


class JobCancelledError(ApplicationError):
    error_code = "JOB_CANCELLED"


class RetryableJobError(ApplicationError):
    error_code = "JOB_TRANSIENT_ERROR"


class JobNonRetryableError(ApplicationError):
    error_code = "JOB_NON_RETRYABLE_ERROR"


class OutboxLeaseLostError(ApplicationError):
    error_code = "OUTBOX_LEASE_LOST"


class OutboxOwnershipConflictError(ApplicationError):
    error_code = "OUTBOX_OWNERSHIP_CONFLICT"


class AlertNotFoundError(ApplicationError):
    error_code = "ALERT_NOT_FOUND"


class EvaluationNotFoundError(ApplicationError):
    error_code = "EVALUATION_NOT_FOUND"


class EvaluationConflictError(ApplicationError):
    error_code = "EVALUATION_CONFLICT"


class EvaluationExecutionError(ApplicationError):
    error_code = "EVALUATION_EXECUTION_ERROR"


class EvaluationIsolationError(ApplicationError):
    error_code = "EVALUATION_ISOLATION_ERROR"


class RateLimitExceededError(ApplicationError):
    error_code = "RATE_LIMIT_EXCEEDED"


class RequestBodyTooLargeError(ApplicationError):
    error_code = "REQUEST_BODY_TOO_LARGE"

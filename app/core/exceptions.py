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

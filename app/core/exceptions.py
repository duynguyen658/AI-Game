class ApplicationError(Exception):
    error_code = "APPLICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CampaignValidationError(ApplicationError):
    error_code = "CAMPAIGN_VALIDATION_ERROR"


class AuthorizationError(ApplicationError):
    error_code = "AUTHORIZATION_ERROR"


class LLMResponseError(ApplicationError):
    error_code = "LLM_RESPONSE_ERROR"


class WorkflowLimitError(ApplicationError):
    error_code = "WORKFLOW_LIMIT_ERROR"


class InvalidStateTransitionError(ApplicationError):
    error_code = "INVALID_STATE_TRANSITION"
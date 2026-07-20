from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ApplicationError,
    ApprovalAlreadyDecidedError,
    ApprovalNotAllowedError,
    AuthenticationError,
    AuthorizationError,
    CampaignAlreadyExistsError,
    CampaignNotFoundError,
    DatabaseUnavailableError,
    InvalidStateTransitionError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
    PersistenceError,
    VersionConflictError,
    WorkflowAlreadyActiveError,
    WorkflowCreationNotAllowedError,
    WorkflowExecutionError,
    WorkflowLimitError,
    WorkflowNotFoundError,
)

ERROR_STATUS_MAP: dict[type[ApplicationError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    ApprovalNotAllowedError: status.HTTP_403_FORBIDDEN,
    CampaignNotFoundError: status.HTTP_404_NOT_FOUND,
    WorkflowNotFoundError: status.HTTP_404_NOT_FOUND,
    CampaignAlreadyExistsError: status.HTTP_409_CONFLICT,
    WorkflowAlreadyActiveError: status.HTTP_409_CONFLICT,
    WorkflowCreationNotAllowedError: status.HTTP_409_CONFLICT,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    ApprovalAlreadyDecidedError: status.HTTP_409_CONFLICT,
    VersionConflictError: status.HTTP_409_CONFLICT,
    WorkflowLimitError: status.HTTP_409_CONFLICT,
    DatabaseUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMProviderError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    LLMResponseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    LLMTimeoutError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    WorkflowExecutionError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    PersistenceError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


async def application_error_handler(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, ApplicationError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Internal server error",
                }
            },
        )
    status_code = ERROR_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)

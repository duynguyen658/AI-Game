from __future__ import annotations

from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.constants import JobErrorClassification
from app.core.exceptions import (
    DatabaseUnavailableError,
    JobLeaseLostError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
    RetryableJobError,
    ToolTimeoutError,
)


EXPLICIT_RETRYABLE_ERRORS = (
    RetryableJobError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderUnavailableError,
    DatabaseUnavailableError,
    ToolTimeoutError,
    JobLeaseLostError,
    OperationalError,
)


def classify_job_error(error: BaseException) -> JobErrorClassification:
    if isinstance(error, EXPLICIT_RETRYABLE_ERRORS):
        return JobErrorClassification.RETRYABLE
    if isinstance(error, DBAPIError) and error.connection_invalidated:
        return JobErrorClassification.RETRYABLE
    return JobErrorClassification.NON_RETRYABLE


def retry_delay_seconds(
    attempt_count: int, *, base_seconds: int, maximum_seconds: int
) -> int:
    if attempt_count < 1:
        return base_seconds
    return min(base_seconds * (2 ** (attempt_count - 1)), maximum_seconds)

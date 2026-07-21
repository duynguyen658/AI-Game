import pytest
from sqlalchemy.exc import OperationalError

from app.core.constants import JobErrorClassification
from app.core.exceptions import (
    ActionExpiredError,
    AuthorizationError,
    CampaignNotFoundError,
    JobPayloadError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
    PolicyDeniedError,
    ToolTimeoutError,
    VersionConflictError,
)
from app.jobs.retry import classify_job_error, retry_delay_seconds
from app.observability.context import get_context, operation_context


def test_retry_delay_is_bounded_exponential() -> None:
    assert retry_delay_seconds(1, base_seconds=5, maximum_seconds=60) == 5
    assert retry_delay_seconds(2, base_seconds=5, maximum_seconds=60) == 10
    assert retry_delay_seconds(10, base_seconds=5, maximum_seconds=60) == 60


def test_operation_context_restores_previous_values() -> None:
    assert get_context() == {}
    with operation_context(correlation_id="outer"):
        assert get_context() == {"correlation_id": "outer"}
        with operation_context(job_id="job-1"):
            assert get_context() == {
                "correlation_id": "outer",
                "job_id": "job-1",
            }
        assert get_context() == {"correlation_id": "outer"}
    assert get_context() == {}


@pytest.mark.parametrize(
    "error",
    [
        LLMTimeoutError("timeout"),
        LLMRateLimitError("rate limit"),
        LLMProviderUnavailableError("unavailable"),
        ToolTimeoutError("tool timeout"),
        OperationalError("SELECT 1", {}, ConnectionError("database down")),
    ],
)
def test_explicit_transient_errors_are_retryable(error: Exception) -> None:
    assert classify_job_error(error) == JobErrorClassification.RETRYABLE


@pytest.mark.parametrize(
    "error",
    [
        JobPayloadError("invalid payload"),
        ActionExpiredError("expired"),
        PolicyDeniedError("denied"),
        AuthorizationError("unauthorized"),
        CampaignNotFoundError("not found"),
        VersionConflictError("version conflict"),
        RuntimeError("unknown exception"),
    ],
)
def test_permanent_and_unknown_errors_are_not_retryable(error: Exception) -> None:
    assert classify_job_error(error) == JobErrorClassification.NON_RETRYABLE

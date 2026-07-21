from app.jobs.retry import retry_delay_seconds
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

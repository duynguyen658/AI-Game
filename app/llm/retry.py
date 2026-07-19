from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.exceptions import LLMProviderError, LLMTimeoutError

OutputT = TypeVar("OutputT")


def with_transient_retry(
    attempts: int,
) -> Callable[[Callable[[], Awaitable[OutputT]]], Callable[[], Awaitable[OutputT]]]:
    return retry(
        retry=retry_if_exception_type((LLMProviderError, LLMTimeoutError)),
        stop=stop_after_attempt(attempts),
        wait=wait_fixed(0),
        reraise=True,
    )

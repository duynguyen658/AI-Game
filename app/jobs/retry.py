from __future__ import annotations


def retry_delay_seconds(
    attempt_count: int, *, base_seconds: int, maximum_seconds: int
) -> int:
    if attempt_count < 1:
        return base_seconds
    return min(base_seconds * (2 ** (attempt_count - 1)), maximum_seconds)

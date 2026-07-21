from app.operations.rate_limit import InMemoryRateLimiter


def test_in_memory_rate_limiter_is_bounded_and_windowed() -> None:
    now = 100.0
    limiter = InMemoryRateLimiter(clock=lambda: now)
    assert limiter.allow("key", limit=2, window_seconds=10)
    assert limiter.allow("key", limit=2, window_seconds=10)
    assert not limiter.allow("key", limit=2, window_seconds=10)
    now = 111.0
    assert limiter.allow("key", limit=2, window_seconds=10)

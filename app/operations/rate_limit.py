from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Protocol

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError


class RateLimiter(Protocol):
    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = self.clock()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


rate_limiter: RateLimiter = InMemoryRateLimiter()


async def enforce_sensitive_rate_limit(request: Request) -> None:
    settings = get_settings()
    actor = request.headers.get("x-actor-id")
    client = request.client.host if request.client else "unknown"
    identity = actor or client
    key = f"{request.method}:{request.url.path}:{identity}"
    if not rate_limiter.allow(
        key,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    ):
        raise RateLimitExceededError("Too many requests for this operation")

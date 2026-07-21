from __future__ import annotations

import time
from uuid import UUID, uuid4

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.observability.context import bind_context, clear_context, reset_context
from app.observability.metrics import HTTP_DURATION, HTTP_ERRORS, HTTP_REQUESTS
from app.observability.tracing import current_trace_id, traced_operation

logger = structlog.get_logger()


def valid_or_new_correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


class OperationalMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        with traced_operation(
            "http.request",
            **{"http.request.method": request.method, "url.path": request.url.path},
        ):
            return await self._dispatch_with_context(request, call_next)

    async def _dispatch_with_context(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > self.settings.max_request_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    {"detail": "Request body is too large"}, status_code=413
                )
        started = time.perf_counter()
        correlation_id = valid_or_new_correlation_id(
            request.headers.get("x-correlation-id")
        )
        request_id = str(uuid4())
        clear_context()
        token = bind_context(
            request_id=request_id,
            correlation_id=correlation_id,
            trace_id=current_trace_id(),
        )
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, correlation_id=correlation_id
        )
        logger.info(
            "http_request_started", method=request.method, path=request.url.path
        )
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        except Exception:
            HTTP_ERRORS.labels(request.method, "unmatched", "500").inc()
            logger.exception("http_request_failed", method=request.method)
            raise
        finally:
            duration = time.perf_counter() - started
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            status_code = response.status_code if response is not None else 500
            HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route_path).observe(duration)
            if status_code >= 400:
                HTTP_ERRORS.labels(request.method, route_path, str(status_code)).inc()
            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "no-referrer"
                response.headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                if self.settings.app_env == "production":
                    response.headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
            logger.info(
                "http_request_completed",
                method=request.method,
                route=route_path,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
            reset_context(token)

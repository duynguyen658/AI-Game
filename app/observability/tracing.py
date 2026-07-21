from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from opentelemetry import trace

from app.core.config import get_settings


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(get_settings().otel_service_name)


@contextmanager
def traced_operation(name: str, **attributes: object) -> Iterator[None]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if span.is_recording():
            for key, value in attributes.items():
                if isinstance(value, (str, bool, int, float)):
                    span.set_attribute(key, value)
        yield


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")

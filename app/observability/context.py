from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Iterator


_context: ContextVar[dict[str, str]] = ContextVar("operation_context", default={})


def get_context() -> dict[str, str]:
    return dict(_context.get())


def get_context_value(name: str) -> str | None:
    return _context.get().get(name)


def bind_context(**values: object | None) -> Token[dict[str, str]]:
    updated = get_context()
    updated.update(
        {key: str(value) for key, value in values.items() if value is not None}
    )
    return _context.set(updated)


def reset_context(token: Token[dict[str, str]]) -> None:
    _context.reset(token)


def clear_context() -> None:
    _context.set({})


@contextmanager
def operation_context(**values: object | None) -> Iterator[dict[str, str]]:
    token = bind_context(**values)
    try:
        yield get_context()
    finally:
        reset_context(token)

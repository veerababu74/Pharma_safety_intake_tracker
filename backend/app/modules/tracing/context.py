"""Request-scoped current span for nested RAG/agent instrumentation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from app.modules.tracing.base import SpanContext

_current_span: ContextVar[SpanContext | None] = ContextVar("obs_current_span", default=None)


def get_current_span() -> SpanContext | None:
    return _current_span.get()


@contextmanager
def bind_span(span: SpanContext | None) -> Iterator[SpanContext | None]:
    token = _current_span.set(span)
    try:
        yield span
    finally:
        _current_span.reset(token)

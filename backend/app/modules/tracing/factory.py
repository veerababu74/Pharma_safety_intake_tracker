"""Tracer factory based on TRACING_MODE config."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import get_settings
from app.modules.tracing.base import SpanContext, Tracer, resolve_span_context
from app.modules.tracing.context import bind_span
from app.modules.tracing.custom_tracer import CustomSQLiteTracer
from app.modules.tracing.langfuse_tracer import LangfuseTracer


class NoOpTracer(Tracer):
    name = "off"

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "span",
        actor: str | None = None,
        role: str | None = None,
        input_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
        parent: SpanContext | None = None,
        existing: SpanContext | None = None,
    ) -> Iterator[SpanContext]:
        ctx = resolve_span_context(
            name, kind=kind, metadata=metadata, parent=parent, existing=existing
        )
        with bind_span(ctx):
            yield ctx


class CompositeTracer(Tracer):
    """Fan-out to custom + Langfuse with identical span identity."""

    name = "both"

    def __init__(self, tracers: list[Tracer]) -> None:
        self._tracers = tracers

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "span",
        actor: str | None = None,
        role: str | None = None,
        input_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
        parent: SpanContext | None = None,
        existing: SpanContext | None = None,
    ) -> Iterator[SpanContext]:
        shared = resolve_span_context(
            name, kind=kind, metadata=metadata, parent=parent, existing=existing
        )
        primary, *rest = self._tracers
        kwargs = {
            "kind": kind,
            "actor": actor,
            "role": role,
            "input_preview": input_preview,
            "metadata": metadata,
            "parent": parent,
            "existing": shared,
        }
        with primary.span(name, **kwargs) as ctx:
            entered = []
            try:
                for t in rest:
                    cm = t.span(name, **kwargs)
                    cm.__enter__()
                    entered.append(cm)
                with bind_span(ctx):
                    yield ctx
            except Exception:
                import sys

                exc = sys.exc_info()
                for cm in reversed(entered):
                    cm.__exit__(*exc)
                raise
            else:
                for cm in reversed(entered):
                    cm.__exit__(None, None, None)


def create_tracer() -> Tracer:
    settings = get_settings()
    mode = settings.tracing_mode
    if mode == "off":
        return NoOpTracer()
    if mode == "langfuse":
        return LangfuseTracer()
    if mode == "custom":
        return CustomSQLiteTracer()
    if mode == "both":
        return CompositeTracer([CustomSQLiteTracer(), LangfuseTracer()])
    return CustomSQLiteTracer()

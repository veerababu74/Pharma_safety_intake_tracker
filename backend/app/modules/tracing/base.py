"""Tracing / observability abstraction."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from uuid import uuid4


def safe_preview(value: Any, limit: int = 4000) -> str:
    """Serialize value for input/output previews without raising."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str = ""
    kind: str = "span"
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_ctx: SpanContext | None = field(default=None, repr=False, compare=False)

    def set_output(self, value: Any, *, limit: int = 4000) -> None:
        self.metadata["output_preview"] = safe_preview(value, limit=limit)

    def update(self, **kwargs: Any) -> None:
        self.metadata.update(kwargs)

    def record_tokens(
        self,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        bubble: bool = True,
        **extra: Any,
    ) -> None:
        """Accumulate input/output tokens on this span and optionally parents."""
        prompt_i = int(prompt_tokens or 0)
        completion_i = int(completion_tokens or 0)
        if total_tokens is None:
            total_i = prompt_i + completion_i
        else:
            total_i = int(total_tokens)
        if prompt_i == 0 and completion_i == 0 and total_i == 0:
            return

        def _add(target: SpanContext) -> None:
            meta = target.metadata
            meta["prompt_tokens"] = int(meta.get("prompt_tokens") or 0) + prompt_i
            meta["completion_tokens"] = int(meta.get("completion_tokens") or 0) + completion_i
            meta["token_usage"] = int(meta.get("token_usage") or 0) + total_i
            for key, value in extra.items():
                if value is not None and key not in meta:
                    meta[key] = value

        _add(self)
        if not bubble:
            return
        parent = self.parent_ctx
        while parent is not None:
            _add(parent)
            parent = parent.parent_ctx


class Tracer(ABC):
    name: str

    @abstractmethod
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
        """
        Create a span.

        - parent: nest under another span (same trace_id)
        - existing: reuse an already-created SpanContext (CompositeTracer fan-out)
        """
        raise NotImplementedError


def new_ids(parent: SpanContext | None = None) -> tuple[str, str, str | None]:
    # OTEL-compatible ids (Langfuse v3+): 32-hex trace, 16-hex span
    trace_id = parent.trace_id if parent else uuid4().hex
    span_id = uuid4().hex[:16]
    parent_span_id = parent.span_id if parent else None
    return trace_id, span_id, parent_span_id


def resolve_span_context(
    name: str,
    *,
    kind: str,
    metadata: dict[str, Any] | None,
    parent: SpanContext | None,
    existing: SpanContext | None,
) -> SpanContext:
    if existing is not None:
        existing.name = existing.name or name
        existing.kind = existing.kind or kind
        if metadata:
            for k, v in metadata.items():
                existing.metadata.setdefault(k, v)
        if parent is not None and existing.parent_ctx is None:
            existing.parent_ctx = parent
            existing.parent_span_id = existing.parent_span_id or parent.span_id
        return existing
    parent = parent or get_parent_fallback()
    trace_id, span_id, parent_span_id = new_ids(parent)
    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        metadata=dict(metadata or {}),
        parent_ctx=parent,
    )


def get_parent_fallback() -> SpanContext | None:
    from app.modules.tracing.context import get_current_span

    return get_current_span()

"""Custom SQLite-backed tracing (local production-style observability)."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.db.models.obs import TraceEvent
from app.db.session import DatabaseKind, db_manager
from app.modules.tracing.base import SpanContext, Tracer, resolve_span_context, safe_preview
from app.modules.tracing.context import bind_span


class CustomSQLiteTracer(Tracer):
    name = "custom"

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
        start = time.perf_counter()
        status = "ok"
        error_message = None
        # Only bind when we own the active request span (not a secondary mirror)
        bind = existing is None
        try:
            if bind:
                with bind_span(ctx):
                    yield ctx
            else:
                yield ctx
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            ctx.metadata["error"] = error_message
            raise
        finally:
            # Avoid double-write when Composite passes the same existing ctx twice
            if existing is not None and ctx.metadata.get("_custom_persisted"):
                return
            latency_ms = (time.perf_counter() - start) * 1000
            final_meta = dict(ctx.metadata)
            final_meta.pop("_custom_persisted", None)
            final_meta.setdefault("latency_ms", round(latency_ms, 3))
            output_preview = final_meta.pop("output_preview", None)
            prompt_tokens = final_meta.get("prompt_tokens")
            completion_tokens = final_meta.get("completion_tokens")
            token_usage = final_meta.get("token_usage")
            try:
                prompt_int = int(prompt_tokens) if prompt_tokens is not None else None
            except (TypeError, ValueError):
                prompt_int = None
            try:
                completion_int = int(completion_tokens) if completion_tokens is not None else None
            except (TypeError, ValueError):
                completion_int = None
            try:
                if token_usage is not None:
                    token_int = int(token_usage)
                elif prompt_int is not None or completion_int is not None:
                    token_int = int(prompt_int or 0) + int(completion_int or 0)
                else:
                    token_int = None
            except (TypeError, ValueError):
                token_int = None
            if token_int is not None:
                final_meta["token_usage"] = token_int
            if prompt_int is not None:
                final_meta["prompt_tokens"] = prompt_int
            if completion_int is not None:
                final_meta["completion_tokens"] = completion_int
            with db_manager.session(DatabaseKind.OBS) as session:
                session.add(
                    TraceEvent(
                        trace_id=ctx.trace_id,
                        span_id=ctx.span_id,
                        parent_span_id=ctx.parent_span_id,
                        name=name,
                        kind=kind,
                        status=status,
                        actor=actor,
                        role=role,
                        input_preview=safe_preview(input_preview, 4000) or None,
                        output_preview=safe_preview(output_preview, 8000) or None,
                        metadata_json=json.dumps(final_meta, ensure_ascii=False, default=str),
                        latency_ms=latency_ms,
                        token_usage=token_int,
                        prompt_tokens=prompt_int,
                        completion_tokens=completion_int,
                        error_message=error_message,
                    )
                )
            ctx.metadata["_custom_persisted"] = True

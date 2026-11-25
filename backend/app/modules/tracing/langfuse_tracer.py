"""Langfuse tracing adapter (SDK v3+/v5, silent no-op if not configured).

Best practices (Langfuse instrumentation skill):
- Nested observations with descriptive names
- generation / retriever / tool / agent typed correctly
- user_id, session_id, tags via metadata / update
- flush on root completion
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import get_settings
from app.core.logging import get_logger
from app.modules.tracing.base import SpanContext, Tracer, resolve_span_context, safe_preview
from app.modules.tracing.context import bind_span

logger = get_logger("langfuse_tracer")


def _as_type(kind: str) -> str:
    k = (kind or "span").lower()
    if k in {"generation", "llm"}:
        return "generation"
    if k in {"retrieval", "retriever", "rag"}:
        return "retriever"
    if k == "tool":
        return "tool"
    if k == "agent":
        return "agent"
    return "span"


def _hex32(value: str) -> str:
    h = (value or "").replace("-", "")
    if len(h) >= 32:
        return h[:32]
    return (h + "0" * 32)[:32]


def _hex16(value: str) -> str:
    h = (value or "").replace("-", "")
    if len(h) >= 16:
        return h[:16]
    return (h + "0" * 16)[:16]


class LangfuseTracer(Tracer):
    name = "langfuse"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = None
        host = settings.langfuse_endpoint()
        if settings.langfuse_public_key and settings.langfuse_secret_key and host:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=host,
                )
                logger.info("langfuse_initialized", host=host)
            except Exception as exc:  # noqa: BLE001
                logger.warning("langfuse_init_failed", error=str(exc))
        else:
            logger.warning("langfuse_not_configured")

    def _trace_context(self, ctx: SpanContext) -> dict[str, str]:
        tc: dict[str, str] = {"trace_id": _hex32(ctx.trace_id)}
        if ctx.parent_span_id:
            tc["parent_span_id"] = _hex16(ctx.parent_span_id)
        return tc

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
        bind = existing is None
        meta = {
            "kind": kind,
            "actor": actor,
            "role": role,
            "local_span_id": ctx.span_id,
            "local_trace_id": ctx.trace_id,
            **(metadata or {}),
        }
        as_type = _as_type(kind)
        model = meta.get("llm_model") or meta.get("model")
        preview = safe_preview(input_preview, 4000) or None

        if self._client is None:
            if bind:
                with bind_span(ctx):
                    yield ctx
            else:
                yield ctx
            return

        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type,
            "input": preview,
            "metadata": meta,
            "trace_context": self._trace_context(ctx),
        }
        if as_type == "generation" and model:
            kwargs["model"] = model

        obs_cm = self._client.start_as_current_observation(**kwargs)
        obs = obs_cm.__enter__()
        try:
            # Enrich root-ish attributes when possible
            try:
                update_kwargs: dict[str, Any] = {}
                if hasattr(obs, "update_trace"):
                    tags = []
                    if meta.get("flow"):
                        tags.append(str(meta["flow"]))
                    if meta.get("intent"):
                        tags.append(f"intent:{meta['intent']}")
                    session_id = meta.get("session_id") or meta.get("thread_id")
                    enrich: dict[str, Any] = {
                        "metadata": {
                            k: v
                            for k, v in {"flow": meta.get("flow"), "role": role}.items()
                            if v
                        }
                    }
                    if actor:
                        enrich["user_id"] = actor
                    if session_id:
                        enrich["session_id"] = str(session_id)
                    if tags:
                        enrich["tags"] = tags
                    if enrich.get("metadata") or enrich.get("user_id") or enrich.get("session_id") or enrich.get("tags"):
                        obs.update_trace(**enrich)
                elif hasattr(obs, "update"):
                    obs.update(metadata=meta)
            except Exception as exc:  # noqa: BLE001
                logger.debug("langfuse_enrich_skipped", error=str(exc))

            if bind:
                with bind_span(ctx):
                    yield ctx
            else:
                yield ctx

            latency_ms = (time.perf_counter() - start) * 1000
            final_meta = {**meta, **ctx.metadata, "latency_ms": round(latency_ms, 3)}
            output = ctx.metadata.get("output_preview")
            end_kwargs: dict[str, Any] = {"output": output, "metadata": final_meta}
            if as_type == "generation" and final_meta.get("llm_model"):
                end_kwargs["model"] = final_meta["llm_model"]
            if final_meta.get("usage"):
                end_kwargs["usage_details"] = final_meta["usage"]
            try:
                if hasattr(obs, "update"):
                    obs.update(**{k: v for k, v in end_kwargs.items() if v is not None})
            except TypeError:
                try:
                    obs.update(output=output)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:
            try:
                if hasattr(obs, "update"):
                    obs.update(output={"error": str(exc)}, level="ERROR")
            except Exception:  # noqa: BLE001
                pass
            obs_cm.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            obs_cm.__exit__(None, None, None)
        finally:
            if ctx.parent_span_id is None:
                try:
                    self._client.flush()
                except Exception:  # noqa: BLE001
                    pass

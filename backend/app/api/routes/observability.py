from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_permission
from app.core.config import get_settings
from app.db.models.core import User
from app.db.models.obs import TraceEvent
from app.db.session import DatabaseKind, db_manager

router = APIRouter(prefix="/observability", tags=["observability"])


def _parse_meta(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {}


def _span_dict_from_row(r: TraceEvent) -> dict:
    """Copy ORM attrs while session is still open."""
    meta = _parse_meta(r.metadata_json)
    prompt = r.prompt_tokens
    if prompt is None:
        prompt = meta.get("prompt_tokens")
    completion = r.completion_tokens
    if completion is None:
        completion = meta.get("completion_tokens")
    total = r.token_usage
    if total is None:
        total = meta.get("token_usage")
    if total is None and (prompt is not None or completion is not None):
        total = int(prompt or 0) + int(completion or 0)
    return {
        "id": r.id,
        "trace_id": r.trace_id,
        "span_id": r.span_id,
        "parent_span_id": r.parent_span_id,
        "name": r.name,
        "kind": r.kind,
        "status": r.status,
        "actor": r.actor,
        "role": r.role,
        "input_preview": r.input_preview,
        "output_preview": r.output_preview,
        "metadata": meta,
        "latency_ms": r.latency_ms,
        "token_usage": total,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _token_totals(spans: list[dict]) -> dict[str, int]:
    prompt = 0
    completion = 0
    total = 0
    for span in spans:
        p = span.get("prompt_tokens")
        c = span.get("completion_tokens")
        t = span.get("token_usage")
        if p is None and c is None and t is None:
            continue
        prompt += int(p or 0)
        completion += int(c or 0)
        if t is not None:
            total += int(t)
        else:
            total += int(p or 0) + int(c or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "token_usage": total,
    }


def _tokens_by_span(spans: list[dict]) -> list[dict]:
    """Per-agent / per-span token breakdown (only spans that consumed tokens)."""
    rows: list[dict] = []
    for span in spans:
        prompt = int(span.get("prompt_tokens") or 0)
        completion = int(span.get("completion_tokens") or 0)
        total = int(span.get("token_usage") or (prompt + completion))
        if total <= 0 and prompt <= 0 and completion <= 0:
            continue
        meta = span.get("metadata") or {}
        rows.append(
            {
                "span_id": span.get("span_id"),
                "name": span.get("name"),
                "kind": span.get("kind"),
                "step": meta.get("step"),
                "llm_role": meta.get("llm_role"),
                "llm_provider": meta.get("llm_provider") or meta.get("provider"),
                "llm_model": meta.get("llm_model"),
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "token_usage": total,
            }
        )
    rows.sort(key=lambda r: r.get("token_usage") or 0, reverse=True)
    return rows


@router.get("/config")
def obs_config(user: User = Depends(require_permission("obs:view"))):
    settings = get_settings()
    return {
        "tracing_mode": settings.tracing_mode,
        "langfuse_configured": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
        "langfuse_host": settings.langfuse_endpoint(),
        "custom_sqlite": True,
        "groq_pool_size": len(settings.groq_api_key_pool()),
        "llm_fallback": {
            "enabled": settings.llm_fallback_enabled,
            "provider": settings.llm_fallback_provider,
            "model": settings.llm_fallback_model,
            "api_key_configured": bool(settings.provider_api_key(settings.llm_fallback_provider)),
        },
        "llm_roles": settings.llm_roles_summary(),
    }


@router.get("/spans")
def list_spans(
    limit: int = Query(default=200, le=1000),
    flow: str | None = Query(default=None, description="Filter metadata.flow: rag|agent"),
    user: User = Depends(require_permission("obs:view")),
):
    with db_manager.session(DatabaseKind.OBS) as session:
        rows = (
            session.query(TraceEvent)
            .order_by(TraceEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        out = [_span_dict_from_row(r) for r in rows]
    if flow:
        out = [s for s in out if (s.get("metadata") or {}).get("flow") == flow]
    return out


@router.get("/traces")
def list_traces(
    limit: int = Query(default=50, le=200),
    flow: str | None = Query(default=None),
    user: User = Depends(require_permission("obs:view")),
):
    """Grouped traces (production-style list): one row per trace_id."""
    with db_manager.session(DatabaseKind.OBS) as session:
        rows = (
            session.query(TraceEvent)
            .order_by(TraceEvent.created_at.desc())
            .limit(min(limit * 40, 2000))
            .all()
        )
        # Materialize inside the session to avoid DetachedInstanceError
        spans = [_span_dict_from_row(r) for r in rows]

    by_trace: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        by_trace[s["trace_id"]].append(s)

    traces = []
    for trace_id, group in by_trace.items():
        spans_sorted = sorted(group, key=lambda x: x.get("created_at") or "")
        roots = [s for s in spans_sorted if not s.get("parent_span_id")]
        root = roots[0] if roots else spans_sorted[0]
        meta = root.get("metadata") or {}
        if flow and meta.get("flow") != flow and not any(
            (s.get("metadata") or {}).get("flow") == flow for s in spans_sorted
        ):
            continue
        root_latency = root.get("latency_ms")
        total_latency = root_latency if root_latency is not None else sum(
            float(s.get("latency_ms") or 0.0) for s in spans_sorted if not s.get("parent_span_id")
        )
        statuses = {s.get("status") for s in spans_sorted}
        status = "error" if "error" in statuses else "ok"
        tokens = _token_totals(spans_sorted)
        traces.append(
            {
                "trace_id": trace_id,
                "name": root.get("name"),
                "flow": meta.get("flow")
                or next(
                    (
                        (s.get("metadata") or {}).get("flow")
                        for s in spans_sorted
                        if (s.get("metadata") or {}).get("flow")
                    ),
                    None,
                ),
                "status": status,
                "actor": root.get("actor"),
                "role": root.get("role"),
                "span_count": len(spans_sorted),
                "latency_ms": round(float(total_latency or 0.0), 2),
                "input_preview": root.get("input_preview"),
                "output_preview": root.get("output_preview"),
                "intent": meta.get("intent"),
                "llm_model": meta.get("llm_model"),
                "llm_provider": meta.get("llm_provider"),
                "prompt_tokens": tokens["prompt_tokens"],
                "completion_tokens": tokens["completion_tokens"],
                "token_usage": tokens["token_usage"],
                "created_at": root.get("created_at"),
            }
        )

    traces.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return traces[:limit]


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, user: User = Depends(require_permission("obs:view"))):
    with db_manager.session(DatabaseKind.OBS) as session:
        rows = (
            session.query(TraceEvent)
            .filter(TraceEvent.trace_id == trace_id)
            .order_by(TraceEvent.created_at.asc())
            .all()
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Trace not found")
        spans = [_span_dict_from_row(r) for r in rows]
    roots = [s for s in spans if not s.get("parent_span_id")]
    root = roots[0] if roots else spans[0]
    tokens = _token_totals(spans)
    return {
        "trace_id": trace_id,
        "root": root,
        "span_count": len(spans),
        "spans": spans,
        "tree": _build_tree(spans),
        "token_usage": tokens["token_usage"],
        "prompt_tokens": tokens["prompt_tokens"],
        "completion_tokens": tokens["completion_tokens"],
        "tokens_by_span": _tokens_by_span(spans),
    }


def _build_tree(spans: list[dict]) -> list[dict]:
    by_id = {s["span_id"]: {**s, "children": []} for s in spans}
    roots: list[dict] = []
    for s in spans:
        node = by_id[s["span_id"]]
        parent = s.get("parent_span_id")
        if parent and parent in by_id:
            by_id[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots

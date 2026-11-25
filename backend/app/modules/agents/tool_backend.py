"""Agent tool backend selector: local tools.py vs FastMCP.

AGENT_TOOL_BACKEND=local  → LangChain StructuredTools from tools.py (default)
AGENT_TOOL_BACKEND=mcp    → same tool names, invoked through FastMCP Client
                            (in-process mcp_server.server.mcp, or HTTP URL)

Runtime override (demo UI) is stored in-process and cleared on process restart.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.agents.tools import (
    GetReportInput,
    ListReportsInput,
    RagQueryInput,
    SubmitIntakeInput,
    UpdateStatusInput,
    approve_close_tool,
    build_agent_tools,
)

logger = logging.getLogger("agent_tool_backend")

ToolBackend = Literal["local", "mcp"]

_runtime_override: ToolBackend | None = None
_tools_cache: dict[str, StructuredTool] | None = None
_tools_cache_key: str | None = None
_mcp_instance = None


class ApproveCloseArgs(BaseModel):
    reference_id: str
    actor: str = Field(default="mcp_approver")
    role: str = Field(default="approver")
    comment: str | None = Field(default=None)


def get_effective_tool_backend() -> ToolBackend:
    if _runtime_override in {"local", "mcp"}:
        return _runtime_override
    value = (get_settings().agent_tool_backend or "local").strip().lower()
    return "mcp" if value == "mcp" else "local"


def set_runtime_tool_backend(backend: ToolBackend) -> ToolBackend:
    global _runtime_override
    if backend not in {"local", "mcp"}:
        raise ValueError("agent_tool_backend must be 'local' or 'mcp'")
    _runtime_override = backend
    clear_tool_cache()
    logger.info("agent_tool_backend_runtime_set backend=%s", backend)
    return backend


def clear_runtime_tool_backend() -> None:
    global _runtime_override
    _runtime_override = None
    clear_tool_cache()


def clear_tool_cache() -> None:
    global _tools_cache, _tools_cache_key
    _tools_cache = None
    _tools_cache_key = None


def tool_backend_status() -> dict[str, Any]:
    settings = get_settings()
    effective = get_effective_tool_backend()
    return {
        "tool_backend": effective,
        "env_default": (settings.agent_tool_backend or "local").strip().lower(),
        "runtime_override": _runtime_override,
        "options": ["local", "mcp"],
        "mcp_transport": settings.agent_mcp_transport,
        "mcp_url": settings.agent_mcp_url,
        "description": {
            "local": "Call app.modules.agents.tools directly (tools.py)",
            "mcp": "Call the same tools through FastMCP (mcp_server/server.py)",
        },
    }


def get_agent_tool_map() -> dict[str, StructuredTool]:
    global _tools_cache, _tools_cache_key
    backend = get_effective_tool_backend()
    settings = get_settings()
    key = f"{backend}|{settings.agent_mcp_transport}|{settings.agent_mcp_url}"
    if _tools_cache is not None and _tools_cache_key == key:
        return _tools_cache
    tools = build_mcp_agent_tools() if backend == "mcp" else build_agent_tools()
    _tools_cache = {t.name: t for t in tools}
    _tools_cache_key = key
    return _tools_cache


def invoke_approve_close(
    reference_id: str, actor: str, role: str, comment: str | None = None
) -> str:
    if get_effective_tool_backend() == "mcp":
        return _call_mcp_tool(
            "approve_close",
            {
                "reference_id": reference_id,
                "actor": actor,
                "role": role,
                "comment": comment,
            },
        )
    return approve_close_tool(reference_id, actor, role, comment=comment)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=180)


def _load_inprocess_mcp():
    global _mcp_instance
    if _mcp_instance is not None:
        return _mcp_instance
    # tool_backend.py → agents → modules → app → backend → repo root
    root = Path(__file__).resolve().parents[4]
    server_path = root / "mcp_server" / "server.py"
    if not server_path.is_file():
        raise FileNotFoundError(f"MCP server not found: {server_path}")
    spec = importlib.util.spec_from_file_location("novacure_mcp_server", server_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load mcp_server.server")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _mcp_instance = module.mcp
    return _mcp_instance


def _mcp_client_target() -> Any:
    settings = get_settings()
    transport = (settings.agent_mcp_transport or "inprocess").strip().lower()
    if transport == "http":
        return (settings.agent_mcp_url or "http://127.0.0.1:8765/mcp").strip()
    return _load_inprocess_mcp()


def _normalize_mcp_result(result: Any) -> str:
    if result is None:
        return json.dumps({"ok": False, "error": "empty MCP result"})
    if isinstance(result, str):
        return result
    content = getattr(result, "content", None)
    if content:
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        if parts:
            return parts[0] if len(parts) == 1 else json.dumps(parts)
    data = getattr(result, "data", None)
    if data is not None:
        return data if isinstance(data, str) else json.dumps(data, default=str)
    if isinstance(result, dict):
        return json.dumps(result, default=str)
    return str(result)


def _call_mcp_tool(name: str, arguments: dict[str, Any]) -> str:
    try:
        from fastmcp import Client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "AGENT_TOOL_BACKEND=mcp requires fastmcp. pip install fastmcp"
        ) from exc

    async def _run() -> str:
        target = _mcp_client_target()
        async with Client(target) as client:
            result = await client.call_tool(name, arguments)
            return _normalize_mcp_result(result)

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("mcp_tool_failed name=%s", name)
        return json.dumps({"ok": False, "error": f"MCP tool '{name}' failed: {exc}"})


def _mcp_tool(name: str, description: str, args_schema: type[BaseModel]) -> StructuredTool:
    def _func(**kwargs: Any) -> str:
        cleaned = {k: v for k, v in kwargs.items() if v is not None}
        return _call_mcp_tool(name, cleaned)

    return StructuredTool.from_function(
        name=name,
        description=f"{description} [via MCP]",
        func=_func,
        args_schema=args_schema,
    )


def build_mcp_agent_tools() -> list[StructuredTool]:
    """StructuredTools with identical names/schemas; execution goes through MCP."""
    return [
        _mcp_tool(
            "submit_intake_report",
            "Create a fictional intake report (PQC or AE) with mandatory validation.",
            SubmitIntakeInput,
        ),
        _mcp_tool(
            "update_status",
            "Update report status. In Review→Closed requires HITL approval.",
            UpdateStatusInput,
        ),
        _mcp_tool(
            "get_report",
            "Fetch one report by REF-YYYY-XXXX.",
            GetReportInput,
        ),
        _mcp_tool(
            "list_reports",
            "List/filter fictional intake reports by status and type.",
            ListReportsInput,
        ),
        _mcp_tool(
            "hybrid_rag_query",
            "Search SOPs/past reports with hybrid RAG (expanded queries + rerank).",
            RagQueryInput,
        ),
        _mcp_tool(
            "approve_close",
            "Approve pending HITL close.",
            ApproveCloseArgs,
        ),
    ]

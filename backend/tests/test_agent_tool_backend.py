"""Agent tool backend: local tools.py vs FastMCP selector."""

from __future__ import annotations

from app.modules.agents import tool_backend as tb


def setup_function() -> None:
    tb.clear_runtime_tool_backend()
    tb.clear_tool_cache()


def teardown_function() -> None:
    tb.clear_runtime_tool_backend()
    tb.clear_tool_cache()


def test_default_backend_is_local_or_env():
    status = tb.tool_backend_status()
    assert status["tool_backend"] in {"local", "mcp"}
    assert "local" in status["options"]
    assert "mcp" in status["options"]
    assert status["runtime_override"] is None


def test_runtime_override_switches_and_clears_cache():
    assert tb.set_runtime_tool_backend("mcp") == "mcp"
    assert tb.get_effective_tool_backend() == "mcp"
    status = tb.tool_backend_status()
    assert status["tool_backend"] == "mcp"
    assert status["runtime_override"] == "mcp"

    tools = tb.get_agent_tool_map()
    assert "submit_intake_report" in tools
    assert "hybrid_rag_query" in tools
    # MCP wrappers annotate description
    assert "MCP" in (tools["get_report"].description or "")

    tb.set_runtime_tool_backend("local")
    local_tools = tb.get_agent_tool_map()
    assert "submit_intake_report" in local_tools
    assert "MCP" not in (local_tools["get_report"].description or "")


def test_invoke_approve_close_local_path(monkeypatch):
    tb.set_runtime_tool_backend("local")
    calls: list[tuple] = []

    def _fake(ref: str, actor: str, role: str, comment: str | None = None) -> str:
        calls.append((ref, actor, role, comment))
        return '{"ok": true, "report": {"reference_id": "%s", "status": "Closed"}}' % ref

    monkeypatch.setattr(tb, "approve_close_tool", _fake)
    out = tb.invoke_approve_close("REF-2026-9999", "admin", "admin", comment="ok")
    assert calls == [("REF-2026-9999", "admin", "admin", "ok")]
    assert "Closed" in out


def test_invalid_backend_rejected():
    try:
        tb.set_runtime_tool_backend("rpc")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError:
        pass

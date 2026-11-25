"""Smoke: FastMCP demo server wraps the same agent tool callables."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "mcp_server" / "server.py"


@pytest.fixture(scope="module")
def mcp_module():
    pytest.importorskip("fastmcp")
    spec = importlib.util.spec_from_file_location("novacure_mcp_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcp_parity_lists_core_agent_tools(mcp_module):
    payload = json.loads(mcp_module.list_agent_tool_parity())
    for name in (
        "submit_intake_report",
        "update_status",
        "get_report",
        "list_reports",
        "hybrid_rag_query",
    ):
        assert name in payload["mcp_tools"]
        assert name in payload["langgraph_agent_tools"]


def test_mcp_list_reports_returns_json(mcp_module):
    raw = mcp_module.list_reports()
    data = json.loads(raw)
    assert data.get("ok") is True
    assert "reports" in data

"""NovaCure Pharma Intake MCP server (FastMCP demo).

Exposes the **same tools** as the in-app LangGraph agent:
  - submit_intake_report
  - update_status
  - get_report
  - list_reports
  - hybrid_rag_query
  - approve_close  (HITL helper used by the agent control plane)

This is a **local training demo**. Synthetic data only. Never assesses causality,
treatment, or regulatory reportability.

Run (from repo root, backend venv activated):

  cd mcp_server
  python server.py

Or HTTP demo transport:

  python server.py --http --port 8765
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Bootstrap: import the FastAPI backend package (shared SQLite + RAG + tools)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.db.session import db_manager  # noqa: E402
from app.modules.agents import tools as agent_tools  # noqa: E402

db_manager.init()

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover — official SDK fallback
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="NovaCure Pharma Intake MCP",
    instructions=(
        "Local training MCP for fictional pharma intake. "
        "Tools mirror the LangGraph agent: create/list/get reports, update status "
        "(HITL for close), approve_close, and hybrid_rag_query. "
        "Synthetic data only — no causality, treatment, or reportability decisions."
    ),
)


@mcp.tool
def submit_intake_report(
    report_type: str,
    product_name: str,
    batch_lot_number: str,
    date_received: str,
    reporter_type: str,
    description: str,
    actor: str = "mcp_operator",
    role: str = "operator",
    event_description: Optional[str] = None,
    event_onset_date: Optional[str] = None,
) -> str:
    """Create a fictional intake report (PQC or AE). Lot must match LOT-#####."""
    return agent_tools._submit_intake_report(
        report_type=report_type,
        product_name=product_name,
        batch_lot_number=batch_lot_number,
        date_received=date_received,
        reporter_type=reporter_type,
        description=description,
        event_description=event_description,
        event_onset_date=event_onset_date,
        actor=actor,
        role=role,
    )


@mcp.tool
def update_status(
    reference_id: str,
    new_status: str,
    actor: str = "mcp_reviewer",
    role: str = "reviewer",
    reviewer_notes: Optional[str] = None,
) -> str:
    """Update report status. New→In Review, or request Closed (needs reviewer_notes + HITL)."""
    return agent_tools._update_status(
        reference_id=reference_id,
        new_status=new_status,
        actor=actor,
        role=role,
        reviewer_notes=reviewer_notes,
    )


@mcp.tool
def get_report(reference_id: str) -> str:
    """Fetch one fictional report by REF-YYYY-XXXX."""
    return agent_tools._get_report(reference_id)


@mcp.tool
def list_reports(
    status: Optional[str] = None,
    report_type: Optional[str] = None,
    batch_lot_number: Optional[str] = None,
) -> str:
    """List/filter fictional intake reports by status, type, and/or lot."""
    return agent_tools._list_reports(
        status=status,
        report_type=report_type,
        batch_lot_number=batch_lot_number,
    )


@mcp.tool
def hybrid_rag_query(
    question: str,
    actor: str = "mcp_operator",
    role: str = "operator",
) -> str:
    """Search SOPs / digests with the same hybrid RAG pipeline (BM25+dense+RRF+rerank)."""
    return agent_tools._hybrid_rag_query(question=question, actor=actor, role=role)


@mcp.tool
def approve_close(
    reference_id: str,
    actor: str = "mcp_approver",
    role: str = "approver",
    comment: Optional[str] = None,
) -> str:
    """Approve a pending HITL close (optional comment).

    Local demo only: caller-supplied actor/role are accepted for in-process training.
    Do not expose HTTP MCP beyond 127.0.0.1 without auth.
    """
    from app.auth.roles import has_permission

    safe_role = (role or "approver").strip().lower()
    if not has_permission(safe_role, "workflow:approve_close"):
        return json.dumps(
            {
                "ok": False,
                "error": "role lacks workflow:approve_close (use approver or admin)",
            }
        )
    return agent_tools.approve_close_tool(
        reference_id, actor or "mcp_approver", safe_role, comment=comment
    )


@mcp.tool
def list_agent_tool_parity() -> str:
    """Demo helper: show MCP tools vs LangGraph agent tools (parity checklist)."""
    return json.dumps(
        {
            "mcp_tools": [
                "submit_intake_report",
                "update_status",
                "get_report",
                "list_reports",
                "hybrid_rag_query",
                "approve_close",
                "list_agent_tool_parity",
            ],
            "langgraph_agent_tools": [
                "submit_intake_report",
                "update_status",
                "get_report",
                "list_reports",
                "hybrid_rag_query",
            ],
            "note": (
                "MCP wraps the same Python callables in app.modules.agents.tools. "
                "approve_close is exposed here for HITL demos; the chat agent pauses "
                "and resumes via the Approvals UI / HITL resolve API."
            ),
            "guardrails": [
                "LOT-##### validation",
                "HITL for In Review → Closed",
                "Synthetic data only",
                "No causality / treatment / reportability",
            ],
        },
        indent=2,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="NovaCure Pharma Intake FastMCP server")
    parser.add_argument("--http", action="store_true", help="Serve over HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.http:
        host = (args.host or "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost", "::1"} and os.getenv(
            "ALLOW_MCP_REMOTE", ""
        ).strip().lower() not in {"1", "true", "yes"}:
            raise SystemExit(
                f"Refusing MCP HTTP bind to {host!r}. Use 127.0.0.1 or set ALLOW_MCP_REMOTE=true."
            )
        # Prefer streamable HTTP when supported by the installed FastMCP version.
        try:
            mcp.run(transport="http", host=host, port=args.port)
        except TypeError:
            mcp.run(transport="sse", host=host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()

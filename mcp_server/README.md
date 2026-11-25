# NovaCure Pharma Intake — FastMCP Server (demo)

Local MCP server that exposes the **same tools** the LangGraph agent uses inside the app.

> Training / presentation only. Synthetic data. Same hard bans as `CLAUDE.md`.

## Why this exists

Capstone slide: **MCP & Plugin Integration**.  
The product agent already has tools in `backend/app/modules/agents/tools.py`. This folder wraps those callables with **FastMCP** so an external MCP client (Cursor, Claude Desktop, MCP Inspector) can call them over stdio/HTTP.

```text
MCP client  ──stdio/HTTP──►  mcp_server/server.py
                                  │
                                  ▼
                     app.modules.agents.tools
                                  │
                     ReportService / HybridRAGPipeline
                                  │
                     local SQLite + Chroma (same as FastAPI)
```

## Tools (parity)

| MCP tool | Agent tool | Purpose |
|---|---|---|
| `submit_intake_report` | ✅ | Create PQC/AE (`LOT-#####`) |
| `update_status` | ✅ | New → In Review / request Closed |
| `get_report` | ✅ | Lookup `REF-YYYY-XXXX` |
| `list_reports` | ✅ | Filter by status / type |
| `hybrid_rag_query` | ✅ | Hybrid RAG over SOPs |
| `approve_close` | HITL helper | Approver close for demos |
| `list_agent_tool_parity` | demo | Show mapping / guardrails |

## Setup

```bash
cd backend
.\.venv\Scripts\activate
pip install -r ..\mcp_server\requirements.txt
```

## Run

**stdio** (default — what Cursor / Claude Desktop use):

```bash
cd mcp_server
python server.py
```

**HTTP** (easy browser/inspector demo):

```bash
python server.py --http --port 8765
```

## Wire into Cursor (optional)

1. Copy `cursor.mcp.example.json` into your Cursor MCP settings (or merge the `mcpServers` block).
2. Fix the absolute paths to your machine.
3. Restart Cursor → Tools should list `novacure-pharma-intake`.

## Demo script (manager)

1. Open MCP Inspector or Cursor MCP tools.
2. Call `list_agent_tool_parity` → show same names as LangGraph.
3. Call `list_reports` with `status=New`.
4. Call `hybrid_rag_query` with:  
   `What should we do for a packaging complaint on LOT-88392?`
5. Optionally create a fictional PQC via `submit_intake_report`, then show the same REF on the web Dashboard.

## Do not confuse with

| This MCP server | In-app Agent Chat |
|---|---|
| External protocol for IDE/demo clients | React UI → FastAPI → LangGraph |
| Same Python tools underneath | Same Python tools underneath |

Both share `backend` data. Prefer one writer at a time during demos.

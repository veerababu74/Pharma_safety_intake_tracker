# Backend Documentation

In-depth FastAPI backend guides for the **Pharma Safety Intake Tracker**.

Each core doc includes simple English, Mermaid diagrams, and **INPUT → OUTPUT** examples.

> Synthetic / training data only. No causality, treatment, or regulatory reportability decisions.

## Read in this order

| # | Document | What you will learn |
|---|---|---|
| 1 | [Architecture & Technologies](./01_ARCHITECTURE.md) | Structure, stack, 4 DBs, factories |
| 2 | [Authentication, Roles & Responsibilities](./02_AUTHENTICATION_ROLES.md) | Login/JWT/permissions |
| 3 | [RAG](./03_RAG.md) | Upload → hybrid search → answer |
| 4 | [Agent](./04_AGENT.md) | LangGraph router, tools, HITL |
| 5 | [Tracing & Monitoring](./05_TRACING_MONITORING.md) | Custom traces, Langfuse, audit |
| 6 | [End-to-End Backend Solution](./06_END_TO_END_BACKEND.md) | Full-day backend story |
| 7 | [Reports & Workflow](./07_REPORTS_WORKFLOW.md) | ReportService, REF, pending close |
| 8 | [LLM Providers](./08_LLM_PROVIDERS.md) | Roles, Groq pool, fallback, tokens |
| 9 | [Config & `.env` Reference](./09_CONFIG_ENV_REFERENCE.md) | Full settings catalog |
| 10 | [Evaluation & Testing](./10_EVALUATION_TESTING.md) | pytest map, RAGAS, Locust |
| 11 | [MCP & Chat Sessions](./11_MCP_CHAT_SESSIONS.md) | Tool backend + sessions/HITL rows |
| 12 | [Chunking Strategies](./12_CHUNKING_STRATEGIES.md) | recursive · semantic · structure · agentic · page |

## Coverage checklist (recheck result)

| Backend area | Covered in |
|---|---|
| Folder structure / factories / 4 DBs | 01, 06 |
| Auth / RBAC / seed users | 02 |
| Hybrid RAG pipeline / delete / dedupe | 03 |
| LangGraph agent / breaker / HITL interrupt | 04, 11 |
| Custom + Langfuse tracing / audit streams | 05 |
| E2E day script | 06 |
| ReportService state machine (deep) | 07 |
| LLM roles / resilience / instrumentation | 08 |
| Full `.env` catalog | 09 |
| Eval / RAGAS / Locust / pytest map | 10 |
| MCP tool_backend + chat sessions | 11 |
| **Chunking strategies (deep)** | **12** ← was missing as dedicated doc |
| External MCP client demo | `mcp_server/README.md` |
| System health/providers | 09 |

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

```bash
pytest
python -m evaluation.run_eval --mode both --force-heuristic
```

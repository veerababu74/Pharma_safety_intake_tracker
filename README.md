# Pharma Safety Intake & Triage Tracker

Production-oriented **split-stack** training prototype:

- **Frontend:** React + Vite + TypeScript  
- **Backend:** FastAPI + SQLAlchemy + LangChain/LangGraph-ready agent/RAG  
- **Data:** multiple local SQLite databases (core / audit / rag / observability)  
- **Pluggable:** embeddings, vector DBs via **LangChain FAISS / LangChain Chroma**, LLMs, storage, tracing  

> Fictional data only. Never assesses causality, treatment, or regulatory reportability.

## Quick start

### Backend
```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

### Frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

UI: http://127.0.0.1:5173

## Sample users (2 per role)

| Username | Password | Role |
|---|---|---|
| admin | Admin@123 | admin |
| admin2 | Admin2@123 | admin |
| reviewer | Reviewer@123 | reviewer |
| reviewer2 | Reviewer2@123 | reviewer |
| operator | Operator@123 | operator |
| operator2 | Operator2@123 | operator |
| approver | Approver@123 | approver |
| approver2 | Approver2@123 | approver |

## Configuration highlights (backend `.env`)

- `EMBEDDING_PROVIDER` = `sentence_transformers` | `huggingface` | `openai` | `google`
- `VECTOR_STORE_PROVIDER` = `faiss` | `chromadb`
- `LLM_PROVIDER` = `openai` | `groq` | `google` | `openrouter` | `mistral` | `mock`
- `TRACING_MODE` = `custom` | `langfuse` | `both` | `off`
- `STORAGE_PROVIDER` = `local` (Azure/S3/GCS adapters stubbed for future)

## Multi-database layout

| DB | Purpose |
|---|---|
| `data/core.db` | Users + intake reports |
| `data/audit.db` | Audit middleware + domain audit events |
| `data/rag.db` | Document/chunk tracking |
| `data/observability.db` | Custom tracing spans |

## Key features

- Intake validation + REF IDs + dashboard filters  
- Status workflow New → In Review → Closed with HITL approval  
- Admin document upload with chunk strategy / size / overlap (`recursive`, `semantic`, `structure_aware`, `agentic`, `page_based`)  
- View + delete documents (storage + vector index)  
- Hybrid RAG (BM25 + dense + RRF + rerank)  
- LangGraph router agent + tools + SQLite checkpointer HITL + per-user chat sessions/history in core DB  
- Custom monitoring panel for admin/reviewer  
- Evaluation under `backend/evaluation/` (classic retrieval metrics + **RAGAS**)  
- Pytest suite under `backend/tests/`

### Evaluation

```bash
cd backend
python -m evaluation.run_eval --mode both
# RAGAS only (uses configured LLM when available; else heuristic fallback)
python -m evaluation.run_eval --mode ragas
# Offline / CI without LLM judges
python -m evaluation.run_eval --mode ragas --force-heuristic
```

Report written to `backend/evaluation/last_eval_report.json`.

## Sample knowledge files + how to use

See `sample_data/` (txt/pdf/docx/csv/json).

**End-to-end guide (Chroma index → operator 5 reports → reviewer → approver → Agent/RAG):**  
[`docs/HOW_TO_USE.md`](docs/HOW_TO_USE.md)

**Easiest explanation (toy-shop story + visual flows):**  
[`docs/SIMPLE_STORY_GUIDE.md`](docs/SIMPLE_STORY_GUIDE.md)

```bash
cd backend
# VECTOR_STORE_PROVIDER=chromadb in .env
python ..\sample_data\index_to_chromadb.py
```

Or upload from **Admin Docs** while logged in as admin.

## Architecture notes

Backend modules follow **Strategy / Factory / DIP**:

- `app/modules/embeddings`
- `app/modules/vectorstores`
- `app/modules/llms`
- `app/modules/storage`
- `app/modules/chunking`
- `app/modules/tracing`
- `app/db` (adaptable engine registry)

Frontend loads API base from `VITE_API_BASE_URL`, else hardcoded `http://127.0.0.1:8000/api/v1`.

## Capstone requirements matrix

| ID | Requirement | Where to look |
|---|---|---|
| F1 | Auto REF IDs | `backend/app/services/report_service.py` · Intake UI |
| F2–F5 | Report types, fields, AE gates, validation | Intake page · `report_service.create` |
| F6 | Dashboard filters | `frontend/src/pages/DashboardPage.tsx` |
| F7 | Status lifecycle | Dashboard + `ALLOWED` transitions |
| F8 | Local audit trail | Audit Trail page · `audit.db` · `/audit/logs` |
| F9 | Hybrid RAG 4 stages | Knowledge Query · `modules/rag/pipeline.py` |
| F10 | Admin doc injection | Admin Docs · `document_service.py` |
| F11 | Agent router + tools | Agent Chat · `modules/agents/graph.py` |
| F12 | HITL on close | HITL Approvals · approve/reject-close |
| F13 | Circuit breaker | Agent tools · `tests/test_agent_breaker.py` |
| G1 | `CLAUDE.md` | repo root |
| G2 | Plan Mode plan | `docs/IMPLEMENTATION_PLAN.md` |
| G3 | Review skill | `.claude/skills/pharma-intake-review/SKILL.md` |
| G4 | Governance hook + log | `.cursor/hooks.json` · `.governance/edit-audit.jsonl` |
| G5 | Automated tests | `cd backend && pytest` |
| G6 | Demo evidence | `docs/DEMO_WALKTHROUGH.md` |

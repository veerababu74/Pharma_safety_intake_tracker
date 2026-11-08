# Implementation Architecture (React + FastAPI)

## Runtime topology

```
React (Vite :5173)  --HTTP JWT-->  FastAPI (:8000)
                                      |
          +---------------------------+---------------------------+
          |                           |                           |
     core.db (users/reports)   audit.db (middleware)      rag.db (docs)
                                      |
                               observability.db (custom traces)
                                      |
                     FAISS/Chroma + local uploads directory
```

## Backend package map

| Path | Responsibility |
|---|---|
| `app/core` | Settings, logging, security, DI container |
| `app/db` | Multi-SQLite engines + models (Factory/Registry) |
| `app/middleware` | Audit HTTP middleware |
| `app/auth` | Roles, JWT deps, seeded users |
| `app/modules/embeddings` | Strategy + factory (ST / OpenAI / Google / hash fallback) |
| `app/modules/vectorstores` | LangChain FAISS / LangChain Chroma adapters (config-switched) |
| `app/modules/llms` | OpenAI / Groq / Google / OpenRouter / Mistral / mock |
| `app/modules/storage` | Local now; Azure/S3/GCS stubs |
| `app/modules/chunking` | recursive / semantic / structure_aware / agentic / page_based |
| `app/modules/rag` | BM25 + dense + RRF + rerank pipeline |
| `app/modules/agents` | Router + validation + STM + circuit breaker |
| `app/modules/tracing` | custom SQLite / Langfuse / both / off |
| `app/api/routes` | REST endpoints |
| `evaluation/` | precision/recall/MRR/nDCG/F1/grounding/refusal |
| `tests/` | pytest |

## Frontend map

| Path | Responsibility |
|---|---|
| `src/config.ts` | `VITE_API_BASE_URL` with hardcoded fallback |
| `src/api/client.ts` | Shared fetch wrapper |
| `src/auth` | Auth context + role helpers |
| `src/components` | Reusable UI + shell |
| `src/pages` | Login, Dashboard, Intake, Approvals, RAG, Admin Docs, Monitoring, Audit |

## Config switches (no code changes)

Set in `backend/.env`:

- embedding / vector store / LLM / storage / tracing mode
- API keys for cloud providers when needed

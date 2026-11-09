# 01 — Backend Architecture & Technologies

### In-depth guide with visuals + input → output examples

> Goal of this file: anyone should understand **how the backend is shaped**, **what each technology does**, and **what goes in / what comes out** at every major step.

---

## Quick map

| Section | What you learn |
|---|---|
| [1. Backend in plain English](#1-backend-in-plain-english) | What this service is |
| [2. Big architecture picture](#2-big-architecture-picture) | Boxes and arrows |
| [3. Layer cake (request path)](#3-layer-cake-request-path) | Input → each layer → output |
| [4. Folder structure in depth](#4-folder-structure-in-depth) | Every important folder |
| [5. Technologies dictionary](#5-technologies-dictionary) | Stack with examples |
| [6. Four databases + indexes](#6-four-databases--indexes) | What data lands where |
| [7. Vector DB & embeddings](#7-vector-db--embeddings) | FAISS/Chroma I/O |
| [8. Factories & container](#8-factories--container) | How providers are swapped |
| [9. Startup sequence](#9-startup-sequence) | Boot input → ready output |
| [10. Mini E2E on architecture](#10-mini-e2e-on-architecture) | One create-report walk |

---

## 1. Backend in plain English

The backend is the **brain + rulebook + memory** of the Pharma Safety Intake Tracker.

| If the UI is… | The backend is… |
|---|---|
| A reception desk screen | The clerk who checks ID, stamps forms, files records |
| Buttons and forms | Validation, permissions, workflow, AI tools |
| What users *see* | What the system *allows* and *remembers* |

**Base URL:** `http://127.0.0.1:8000`  
**API prefix:** `/api/v1`  
**Swagger UI:** `http://127.0.0.1:8000/docs`

### Concept: request / response

```mermaid
flowchart LR
  IN["INPUT\nHTTP request\n+ JSON body\n+ Bearer token"] --> BE["BACKEND\nvalidate · decide · save · AI"]
  BE --> OUT["OUTPUT\nHTTP status\n+ JSON body\n+ side effects\n(DB / audit / traces)"]
```

---

## 2. Big architecture picture

```mermaid
flowchart TB
  subgraph Clients
    FE[React Frontend]
    SW[Swagger / curl / Postman]
  end

  Clients -->|HTTPS JSON| API[FastAPI app.main]

  API --> MW[CORS + Audit middleware]
  MW --> R[API Router /api/v1]

  R --> AUTH[auth routes]
  R --> REP[reports routes]
  R --> RAG[rag routes]
  R --> AGT[agent routes]
  R --> OBS[observability routes]
  R --> AUD[audit routes]
  R --> SYS[system routes]

  AUTH & REP & AGT --> CORE[(core.db)]
  AUD --> AUDDB[(audit.db)]
  RAG --> RAGDB[(rag.db)]
  RAG --> VEC[(FAISS / Chroma)]
  OBS --> OBSDB[(observability.db)]
  AGT --> CKPT[(langgraph_checkpoints.sqlite)]

  RAG & AGT --> CTR[AppContainer\nembeddings · LLMs · tracer · storage]
```

### Same picture as a “who talks to whom” table

| From | To | Why |
|---|---|---|
| Frontend | FastAPI | All business calls |
| Routes | Services | Keep HTTP thin |
| Services | DB models | Persist truth |
| RAG/Agent | Container | Shared AI engines |
| Everything important | Audit / Obs | Proof + visibility |

---

## 3. Layer cake (request path)

### Concept: layered architecture

```mermaid
flowchart TB
  L1["1. Route layer\nparse HTTP"] --> L2["2. Auth layer\nwho + permission"]
  L2 --> L3["3. Schema layer\nshape validation"]
  L3 --> L4["4. Service layer\nbusiness rules"]
  L4 --> L5["5. Module / DB layer\nengines + SQL"]
  L5 --> L6["6. Side effects\naudit · traces · files"]
```

### Example A — Create report (happy path)

#### INPUT (client → backend)

```http
POST /api/v1/reports
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json
```

```json
{
  "report_type": "Product Quality Complaint",
  "product_name": "CardioMax 50mg",
  "batch_lot_number": "LOT-00045",
  "date_received": "2026-11-08",
  "reporter_type": "Healthcare Professional",
  "description": "Blister foil torn on two packs."
}
```

#### What each layer does

| Layer | Input it receives | Output it produces |
|---|---|---|
| Route | Raw HTTP | Calls service with dict + actor |
| Auth | Bearer token | `User(username=operator, role=operator)` or 401/403 |
| Schema | JSON body | Valid `ReportCreate` or 422 |
| Service | Valid payload | New `Report` row + domain audit |
| DB | ORM object | Persisted `REF-2026-0001` |
| Middleware | Whole request | HTTP audit row |

#### OUTPUT (backend → client)

```json
{
  "reference_id": "REF-2026-0001",
  "report_type": "Product Quality Complaint",
  "product_name": "CardioMax 50mg",
  "batch_lot_number": "LOT-00045",
  "status": "New",
  "pending_close": false,
  "created_by": "operator"
}
```

HTTP status: **201/200** (as implemented) + side effects in `core.db` and `audit.db`.

### Example B — Same call, bad LOT (failure path)

#### INPUT

```json
{
  "report_type": "Product Quality Complaint",
  "product_name": "CardioMax 50mg",
  "batch_lot_number": "45?",
  "date_received": "2026-11-08",
  "reporter_type": "Healthcare Professional",
  "description": "Blister foil torn"
}
```

#### OUTPUT

```json
{
  "detail": "batch_lot_number must match LOT-#####"
}
```

HTTP status: **400/422-style error** (validation).  
**No report row created.** Architecture lesson: bad data dies at the rule layer.

```mermaid
flowchart LR
  IN["INPUT LOT-45?"] --> VAL{"LOT-##### ?"}
  VAL -->|no| ERR["OUTPUT error\nDB unchanged"]
  VAL -->|yes| OK["OUTPUT REF-...\nDB row created"]
```

---

## 4. Folder structure in depth

```text
backend/
├── app/
│   ├── main.py                 # create app, lifespan, middleware
│   ├── api/
│   │   ├── router.py           # mounts route modules
│   │   └── routes/             # one file per domain
│   ├── auth/                   # roles, deps, seed users
│   ├── core/                   # config, security, container, logging
│   ├── db/                     # multi-DB session + models
│   ├── middleware/             # HTTP audit
│   ├── schemas/                # Pydantic request/response models
│   ├── services/               # business logic
│   └── modules/                # pluggable engines (RAG, agent, LLM…)
├── data/                       # sqlite files, uploads, indexes
├── tests/
├── evaluation/
├── requirements.txt
└── .env.example
```

### Concept: “where does new code go?”

| You want to… | Put it in… | Example |
|---|---|---|
| Add an HTTP endpoint | `api/routes/` | new report filter |
| Change close rules | `services/report_service.py` | require notes |
| Swap vector DB | env + `modules/vectorstores/` | FAISS → Chroma |
| Change AI refusal text | `modules/*/prompts.py` | guardrails |
| Add a table | `db/models/` + migration helper | new column |

### Visual: dependency direction

```mermaid
flowchart TB
  routes["api/routes"] --> services["services"]
  routes --> auth["auth/deps"]
  services --> modules["modules/*"]
  services --> db["db/models + session"]
  modules --> core["core/container + config"]
  auth --> db
  auth --> core
```

Routes depend inward. **Modules do not import routes.** That keeps architecture clean.

---

## 5. Technologies dictionary

### Web & data

| Tech | Role | Tiny example |
|---|---|---|
| **FastAPI** | HTTP framework | `@router.post("/reports")` |
| **Uvicorn** | Runs the app | `uvicorn app.main:app --port 8000` |
| **Pydantic** | Validate bodies | reject unknown `report_type` |
| **SQLAlchemy** | ORM to SQLite | `session.add(Report(...))` |
| **python-jose** | JWT encode/decode | login token |
| **passlib/bcrypt** | Hash passwords | store hash, never plain text |
| **structlog** | Structured logs | startup provider summary |

### AI stack

| Tech | Role | Tiny example |
|---|---|---|
| **LangChain** | loaders/splitters helpers | PDF → text |
| **LangGraph** | agent graph + interrupt | pause on close |
| **FAISS / Chroma** | dense vector index | similar chunk search |
| **sentence-transformers** | local embeddings | text → vector |
| **rank-bm25** | keyword retrieval | exact term boost |
| **OpenAI/Groq/Google…** | optional LLMs | answer / route / draft |
| **Langfuse** | optional cloud traces | export spans |
| **RAGAS** | evaluation | measure answer quality |

### Concept: pluggable vs fixed

```mermaid
flowchart LR
  FIXED["Fixed in this project\nworkflow rules\npermissions\nguardrail policy"] 
  PLUG["Pluggable by .env\nLLM provider\nvector store\nembedding\ntracing mode"]
```

**Input (config):** `VECTOR_STORE_PROVIDER=chromadb`  
**Output (runtime):** container builds `ChromaVectorStore` instead of FAISS — same RAG API.

---

## 6. Four databases + indexes

### Concept: separated notebooks

```mermaid
flowchart TB
  subgraph CORE["core.db — work notebook"]
    U[users]
    R[reports]
    CS[chat_sessions / messages]
    H[agent_hitl_requests]
  end
  subgraph AUDIT["audit.db — stamp notebook"]
    A[audit_logs]
  end
  subgraph RAGDB["rag.db — library catalog"]
    D[rag_documents]
    C[rag_document_chunks]
  end
  subgraph OBS["observability.db — camera log"]
    T[trace_events]
  end
```

| DB | Stores | Example row meaning |
|---|---|---|
| core | live cases & users | `REF-2026-0001` is New |
| audit | proof events | operator created REF… |
| rag | doc inventory | `DOC-abc` has 40 chunks |
| obs | AI spans | retrieval took 120ms |

### Also on disk (not SQL tables, but critical)

| Path | Purpose |
|---|---|
| `data/uploads/` | original SOP files |
| `data/faiss/` or `data/chroma/` | dense vectors |
| `data/langgraph_checkpoints.sqlite` | paused agent graphs |

### Example: one create-report writes where?

#### INPUT

Successful `POST /reports` by `operator`.

#### OUTPUT side effects

```mermaid
flowchart LR
  CALL[POST /reports] --> CORE[(core.db\nreports row)]
  CALL --> DOM[(audit.db\naction=created)]
  CALL --> HTTP[(audit.db\naction=http_request)]
```

No writes to `rag.db` or `observability.db` for a plain REST create (unless tracing wraps something else).

---

## 7. Vector DB & embeddings

### Concept: embedding

**Input text:** `"onset date is required for suspected AE"`  
**Output vector:** a list of numbers (e.g. 384 floats for MiniLM)  
Nearby meanings → nearby numbers.

### Concept: vector search

```mermaid
flowchart LR
  Q["INPUT query text"] --> E["embed_query()"]
  E --> V["vector store similarity_search"]
  V --> H["OUTPUT top chunks\n+ scores"]
```

### Providers

| Setting | Options | Default |
|---|---|---|
| `EMBEDDING_PROVIDER` | sentence_transformers / huggingface / openai / google | sentence_transformers |
| `VECTOR_STORE_PROVIDER` | faiss / chromadb | faiss |

### Example: switching store

#### INPUT (.env change)

```text
VECTOR_STORE_PROVIDER=chromadb
```

#### OUTPUT (behavior)

- New indexes go under `data/chroma`
- API paths stay the same (`/rag/documents`, `/rag/query`)
- Old FAISS files are not auto-migrated → re-upload/reindex needed

---

## 8. Factories & container

### Concept: Factory pattern

**Input:** config string `"faiss"`  
**Output:** object implementing `upsert/search/delete`  
Callers never `if provider == ...` all over routes.

```mermaid
flowchart TB
  ENV[".env values"] --> CTR["AppContainer / factories"]
  CTR --> EMB[EmbeddingProvider]
  CTR --> VS[VectorStore]
  CTR --> LLM[LLM providers by role]
  CTR --> TR[Tracer]
  CTR --> ST[Storage]
  CTR --> PIPE[HybridRAGPipeline]
```

### Example: LLM role split

| Role key | Typical INPUT task | Typical OUTPUT |
|---|---|---|
| `router` | user chat text | intent label `lookup` |
| `rag` | question + chunks | grounded answer |
| `response` | tool facts | friendly markdown card |
| `chunking` | long document text | segment boundaries |

**Input config:**

```text
LLM_PROVIDER=groq
LLM_ROUTER_MODEL=llama-3.1-8b-instant
LLM_RAG_MODEL=openai/gpt-oss-120b
```

**Output:** cheap model routes; stronger model answers from docs.

---

## 9. Startup sequence

```mermaid
sequenceDiagram
  participant U as Uvicorn
  participant L as lifespan
  participant DB as DatabaseManager
  participant S as seed_users
  participant C as get_container
  participant D as DocumentService

  U->>L: process start
  L->>L: logging + SECRET_KEY checks
  L->>DB: init 4 SQLite DBs + tables
  L->>S: insert missing demo users
  L->>C: build embeddings/LLM/tracer
  L->>D: rebuild BM25 from rag.db
  L-->>U: OUTPUT app ready :8000
```

### INPUT

```bash
uvicorn app.main:app --reload --port 8000
```

### OUTPUT (success signals)

- `/api/v1/system/health` returns healthy
- `/docs` loads
- logs show embedding/vector/llm/tracing providers
- BM25 memory warm if docs already indexed

---

## 10. Mini E2E on architecture

### Story

Maya (operator) creates a PQC. Architecture pieces that fire:

```mermaid
sequenceDiagram
  participant UI
  participant MW as Audit middleware
  participant Auth as deps/security
  participant Route as reports route
  participant Svc as ReportService
  participant Core as core.db
  participant Aud as audit.db

  UI->>MW: POST /reports + JWT
  MW->>Auth: decode later / identity for audit
  Auth->>Route: user=operator allowed intake:create
  Route->>Svc: create(payload)
  Svc->>Core: INSERT report
  Svc->>Aud: INSERT domain audit
  MW->>Aud: INSERT http_request audit
  Route-->>UI: REF-2026-0001 JSON
```

| Step | INPUT | OUTPUT |
|---|---|---|
| 1 | Bearer token | authenticated operator |
| 2 | report JSON | validated model |
| 3 | validated model | `REF-2026-0001` |
| 4 | create event | audit proof rows |
| 5 | response body | UI shows new case |

---

## Concept cards (keep these)

### Card 1 — API prefix

- **INPUT:** call `/reports` without prefix  
- **OUTPUT:** 404  
- **Correct INPUT:** `/api/v1/reports`

### Card 2 — Thin routes

- **INPUT:** fat business logic inside route function  
- **OUTPUT:** hard-to-test spaghetti  
- **Preferred:** route → service → module/db

### Card 3 — Multi-DB

- **INPUT:** put traces into `core.db`  
- **OUTPUT:** noisy operational DB, harder audits  
- **Preferred:** obs/audit/rag/core split

---

## What to read next

1. [02 Authentication, Roles & Responsibilities](./02_AUTHENTICATION_ROLES.md) — identity I/O  
2. [03 RAG](./03_RAG.md) — document I/O  
3. [04 Agent](./04_AGENT.md) — chat I/O  
4. [05 Tracing](./05_TRACING_MONITORING.md) — span I/O  
5. [06 End-to-End](./06_END_TO_END_BACKEND.md) — full day script  

---

*Doc 01/6 — Architecture (deep + examples)*

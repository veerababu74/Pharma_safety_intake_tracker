# Pharma Safety Intake & Triage Tracker
## Architecture, Workflows & Complete Understanding Guide

> Read this file to understand **what this project is**, **why it exists**, **what problem it solves**, **how every user/admin scenario flows**, and **how to approach building it**.  
> All Mermaid diagrams render in GitHub, VS Code, Cursor preview, and most Markdown viewers.

---

# PART A — Understand the Capstone First

## A1. What is this project?

It is a **local training web application** for a fictional pharmaceutical company.

Operators receive **product quality complaints** and **suspected adverse event** reports (email/phone → human types into the app). The app must:

1. Capture the report with mandatory fields  
2. Give each report a unique ID (`REF-2026-XXXX`)  
3. Let reviewers move status: **New → In Review → Closed**  
4. Keep an **audit log** of who did what  
5. Let users **ask historical questions** over past reports + SOP documents using a **4-stage Hybrid RAG** pipeline  
6. Run those actions through a **safe agent control plane** (validation, routing, HITL, circuit breaker)

It is **NOT** a real hospital system, **NOT** a doctor, and **NOT** a regulatory decision engine.

---

## A2. Why does this project exist? (The real teaching goal)

There are **two goals** at once:

| Goal | Meaning |
|---|---|
| **Product goal** | Build a working Streamlit intake + triage + RAG app |
| **Process goal** | Learn **AI-assisted engineering with governance**: CLAUDE.md, Plan Mode, review skills, hooks, tests |

PwC-style capstones often test whether you can **use AI tools safely and systematically**, not only whether the UI works.

---

## A3. What problem does it solve?

### Business problem (story)
Today, intake staff use **many Excel sheets**. That causes:

- Missing mandatory fields  
- No clear review status  
- Weak audit trail  
- No smart search over past cases / SOPs  

### Your solution
One **local Streamlit app** + **SQLite** + **validation** + **workflow** + **audit** + **hybrid RAG knowledge agent**.

```mermaid
flowchart LR
  subgraph BEFORE["BEFORE — Broken"]
    E1[Email / Phone]
    E2[Scattered Spreadsheets]
    E3[Missing fields]
    E4[No audit / opaque status]
    E1 --> E2 --> E3 --> E4
  end

  subgraph AFTER["AFTER — Your App"]
    A1[Email / Phone]
    A2[Streamlit Intake]
    A3[Validated SQLite Store]
    A4[Dashboard + Audit + RAG]
    A1 --> A2 --> A3 --> A4
  end

  BEFORE -.->|replace with| AFTER
```

---

## A4. What it must NEVER do (critical)

```mermaid
flowchart TB
  APP[Your Capstone App]
  APP -->|ALLOWED| OK1[Capture fictional reports]
  APP -->|ALLOWED| OK2[Validate + store + track status]
  APP -->|ALLOWED| OK3[Search fictional SOPs / past reports]
  APP -->|FORBIDDEN| BAD1[Assess causality]
  APP -->|FORBIDDEN| BAD2[Recommend treatment]
  APP -->|FORBIDDEN| BAD3[Decide regulatory reportability]
  APP -->|FORBIDDEN| BAD4[Store real patient PII]
  APP -->|FORBIDDEN| BAD5[Replace enterprise PV systems]
```

**Data rule:** synthetic / fictional data only.

---

## A5. Roles in the system (who uses what)

| Role | What they do in the UI |
|---|---|
| **Intake Operator** | Fill new report form, see validation errors, save report |
| **Triage Reviewer / Admin** | Filter dashboard, change status, approve Close (HITL) |
| **Knowledge Admin** | Inject / upload fictional SOP documents into the knowledge base (chunk → embed → vector store) |
| **Query User** | Ask historical questions (“past LOT-88392 cases?”, “SOP quarantine steps?”) |
| **Developer (you)** | Build app + governance artifacts + tests |

> “Admin panel” in this capstone = a **Knowledge / Document Admin** page in Streamlit (local), not a cloud console.

---

# PART B — Big Picture Architecture

## B1. System architecture (all layers)

```mermaid
flowchart TB
  subgraph UI["STREAMLIT UI LAYER"]
    F[Intake Form]
    D[Dashboard / Tracker]
    Q[RAG Query Chat]
    ADM[Admin: Document Injection]
    HITL[HITL Approval Panel]
  end

  subgraph AGENT["AGENT CONTROL PLANE"]
    R[Semantic Router]
    TV[Pydantic Tool Validation]
    STM[Short-Term Memory ReAct]
    CB[Circuit Breaker]
  end

  subgraph CORE["CORE SERVICES"]
    VAL[Validation Engine]
    REF[REF-2026-XXXX Generator]
    WF[Status Workflow Manager]
    AUD[Audit Logger]
  end

  subgraph STORE["LOCAL PERSISTENCE"]
    SQL[(SQLite Reports + Audit)]
    VS[(Local Vector Store)]
    BM[(BM25 Index)]
  end

  subgraph RAG["4-STAGE HYBRID RAG"]
    S1[1 BM25 Sparse]
    S2[2 Bi-Encoder Dense]
    S3[3 RRF Fusion k=60]
    S4[4 Cross-Encoder Rerank]
  end

  F --> VAL --> REF --> SQL
  F --> AUD
  D --> WF --> HITL
  WF --> SQL
  WF --> AUD
  Q --> R --> TV
  R -->|historical| RAG
  R -->|intake| F
  R -->|status| WF
  ADM -->|chunk + embed| VS
  ADM -->|index| BM
  S1 --> S3
  S2 --> S3
  S3 --> S4
  S4 --> Q
  VS --> S2
  BM --> S1
  TV --> STM
  TV --> CB
```

---

## B2. How folders should look (target project shape)

```mermaid
flowchart TB
  ROOT[pwc_capstone]
  ROOT --> CLAUDE[CLAUDE.md]
  ROOT --> GUIDE[Guides / Docs]
  ROOT --> APP[app/]
  ROOT --> TESTS[tests/]
  ROOT --> CLAUDEDIR[.claude/skills/]
  ROOT --> GOV[.governance/]

  APP --> UI[ui/ form dashboard rag admin]
  APP --> MODELS[models/ schemas]
  APP --> SVC[services/ storage validation workflow audit]
  APP --> RAGDIR[rag/ bm25 dense rrf rerank]
  APP --> AGENTDIR[agent/ router tools memory breaker]
  APP --> DATA[data/ seed reports + sops]
```

**Concrete tree:**

```
pwc_capstone/
├── CLAUDE.md
├── ARCHITECTURE_AND_WORKFLOWS.md   ← this file
├── CAPSTONE_COMPLETE_GUIDE.md
├── docs/IMPLEMENTATION_PLAN.md
├── app/
│   ├── main.py                     # Streamlit multipage entry
│   ├── ui/
│   │   ├── intake_form.py
│   │   ├── dashboard.py
│   │   ├── rag_chat.py
│   │   └── admin_docs.py           # document injection panel
│   ├── models/schemas.py
│   ├── services/
│   ├── rag/
│   ├── agent/
│   └── data/sops/ + seed_reports/
├── tests/
├── .claude/skills/pharma-intake-review/SKILL.md
└── .governance/edit-audit.jsonl
```

---

## B3. Data model (what is stored where)

```mermaid
erDiagram
  REPORT ||--o{ AUDIT_EVENT : generates
  REPORT {
    string reference_id PK
    string report_type
    string product_name
    string batch_lot_number
    date date_received
    string reporter_type
    string description
    string event_description
    date event_onset_date
    string status
    datetime created_at
    datetime updated_at
  }
  AUDIT_EVENT {
    int id PK
    datetime timestamp
    string reference_id
    string action
    string actor
    string from_status
    string to_status
    string details
  }
  DOCUMENT ||--o{ CHUNK : split_into
  DOCUMENT {
    string doc_id PK
    string title
    string source_type
    datetime ingested_at
  }
  CHUNK {
    string chunk_id PK
    string doc_id FK
    string text
    int token_estimate
    vector embedding
  }
```

| Store | Holds |
|---|---|
| **SQLite** | Reports, status, audit events, document metadata |
| **BM25 index** | Same chunk texts for keyword search |
| **Vector store** | Chunk embeddings for semantic search (local files / sqlite-vec / chroma local / faiss local) |

---

# PART C — All Scenario Workflows (User → Response)

## C1. Scenario Map (which path for which intent)

```mermaid
flowchart TD
  U[User opens Streamlit app]
  U --> M{What do they want?}
  M -->|New complaint / AE| SC1[Scenario 1: Intake Submit]
  M -->|See / filter cases| SC2[Scenario 2: Dashboard]
  M -->|Move status| SC3[Scenario 3: Workflow + HITL]
  M -->|Ask past SOP / lot question| SC4[Scenario 4: Hybrid RAG Query]
  M -->|Upload SOP / knowledge| SC5[Scenario 5: Admin Doc Injection]
  M -->|Agent chat mix of intents| SC6[Scenario 6: Agentic Orchestration]
```

---

## C2. Scenario 1 — Intake Form (User data → Saved report)

**Actors:** Intake Operator  
**Input:** Form fields  
**Output:** `REF-2026-XXXX` saved + audit “created”

```mermaid
sequenceDiagram
  actor Op as Intake Operator
  participant UI as Streamlit Intake Form
  participant SCH as Pydantic Schema
  participant VAL as Validation Rules
  participant REF as REF Generator
  participant DB as SQLite
  participant AUD as Audit Log

  Op->>UI: Fill product, lot, type, description...
  UI->>SCH: Parse form into ReportCreate model
  alt Schema invalid
    SCH-->>UI: Field type/format errors
    UI-->>Op: Context-sensitive error messages
  else Schema OK
    SCH->>VAL: Mandatory + AE conditional checks
    alt Missing required fields
      VAL-->>UI: e.g. Event onset required for AE
      UI-->>Op: Show errors, do not save
    else Valid
      VAL->>REF: Generate REF-2026-XXXX
      REF->>DB: INSERT report status=New
      DB->>AUD: Log created + timestamp + actor
      AUD-->>UI: Success
      UI-->>Op: Saved with reference ID
    end
  end
```

### Validation logic (plain English)

```mermaid
flowchart TD
  START[Submit clicked] --> CORE{Core fields present?}
  CORE -->|No| ERR1[Error: product / lot / date / reporter / description required]
  CORE -->|Yes| TYPE{Report type?}
  TYPE -->|Product Quality Complaint| SAVE[Save status=New]
  TYPE -->|Suspected Adverse Event| AE{event_description AND onset_date?}
  AE -->|No| ERR2[Error: AE extension fields required]
  AE -->|Yes| LOT{batch matches LOT-##### ?}
  LOT -->|No| ERR3[Error: invalid batch format]
  LOT -->|Yes| SAVE
  SAVE --> AUDIT[Write audit event]
  AUDIT --> DONE[Show REF-2026-XXXX]
```

---

## C3. Scenario 2 — Dashboard (List + Filter)

**Actors:** Reviewer  
**Input:** Filters (status, report type)  
**Output:** Filtered table

```mermaid
flowchart LR
  R[Reviewer] --> D[Dashboard Page]
  D --> Q[Query SQLite]
  Q --> F{Apply filters}
  F -->|status| S[New / In Review / Closed]
  F -->|type| T[AE / PQC]
  F --> TBL[Render table of reports]
  TBL --> R
```

---

## C4. Scenario 3 — Status Lifecycle + HITL Close Gate

**Actors:** Triage Reviewer  
**Rule:** `In Review → Closed` **requires human approval** recorded in audit.

```mermaid
stateDiagram-v2
  [*] --> New: Report created
  New --> InReview: Start review
  InReview --> HITL: Request Close
  HITL --> InReview: Reject / cancel
  HITL --> Closed: Human approves close
  Closed --> [*]
```

```mermaid
sequenceDiagram
  actor Rev as Reviewer
  participant UI as Dashboard / Workflow
  participant WF as Workflow Manager
  participant HITL as HITL Gate
  participant DB as SQLite
  participant AUD as Audit Log

  Rev->>UI: Change New → In Review
  UI->>WF: validate transition
  WF->>DB: update status
  WF->>AUD: log status_changed
  AUD-->>Rev: Updated

  Rev->>UI: Request Close
  UI->>HITL: Freeze pending close
  HITL-->>UI: Show Approve Close panel
  alt Not approved
    HITL-->>Rev: Stay In Review
  else Approved
    Rev->>HITL: Confirm + fictional reviewer name
    HITL->>DB: status=Closed
    HITL->>AUD: log hitl_approved + closed
    AUD-->>Rev: Case closed
  end
```

**Illegal transitions (must reject):** New→Closed, Closed→New, Closed→In Review (unless you explicitly design reopen — default = reject).

---

## C5. Scenario 4 — Hybrid RAG Query (Question → Grounded Answer)

**Actors:** Any user asking historical / SOP questions  
**Input:** Natural language query  
**Output:** Answer grounded on Top-3..Top-5 chunks only

```mermaid
flowchart TB
  Q[User Query] --> R{Semantic Router}
  R -->|historical intent| PIPE[Hybrid RAG Pipeline]

  PIPE --> P1[Stage 1: BM25 sparse<br/>k1=1.2-1.5, b=0.75<br/>Top-50]
  PIPE --> P2[Stage 2: Bi-Encoder dense<br/>512 tok / 64 overlap<br/>Cosine Top-50]

  P1 --> P3[Stage 3: RRF fusion<br/>k=60]
  P2 --> P3
  P3 --> P4[Stage 4: Cross-Encoder rerank<br/>drop score < 0.40<br/>keep Top-3 to Top-5]

  P4 --> CTX[Context chunks]
  CTX --> LLM[LLM / local generator<br/>Answer ONLY from chunks]
  LLM --> ANS{Enough evidence?}
  ANS -->|Yes| OUT[Grounded answer + citations]
  ANS -->|No| NEI[Insufficient evidence in knowledge base]
  OUT --> USER[Response to user]
  NEI --> USER
```

### Why 4 stages? (simple)

| Stage | Catches | Example |
|---|---|---|
| BM25 | Exact codes / lots | `LOT-88392`, `Anaphylaxis` |
| Bi-Encoder | Meaning / synonyms | “hard to breathe” → dyspnea SOP text |
| RRF | Merge both lists fairly | One ranked pool |
| Cross-Encoder | Precision filter | Only strong matches go to the LLM |

---

## C6. Scenario 5 — Admin Panel: Document Injection → Vector DB

This is the part many students miss. **RAG cannot answer about SOPs unless someone puts documents into the knowledge base.**

**Actors:** Knowledge Admin  
**Input:** Upload `.txt` / `.md` fictional SOP (or paste text)  
**Output:** Chunks in BM25 index + embeddings in local vector store

```mermaid
sequenceDiagram
  actor Admin as Knowledge Admin
  participant UI as Admin Docs Page
  participant META as SQLite Doc Metadata
  participant CHK as Chunker 512/64
  participant EMB as Bi-Encoder Embedder
  participant VS as Local Vector Store
  participant BM as BM25 Index
  participant AUD as Audit Log

  Admin->>UI: Upload fictional SOP / past report dump
  UI->>UI: Reject if looks like real PII (basic checks)
  UI->>META: Save doc_id, title, source_type, ingested_at
  UI->>CHK: Split text into overlapping chunks
  CHK->>EMB: Embed each chunk
  EMB->>VS: Upsert vectors + chunk text
  CHK->>BM: Rebuild / update lexical index
  UI->>AUD: Log document_ingested
  AUD-->>Admin: Ingestion complete (N chunks)
```

```mermaid
flowchart LR
  subgraph ADMIN_UI["Admin Panel"]
    U1[Upload / Paste SOP]
    U2[Set title + tags]
    U3[Ingest button]
  end

  subgraph PIPE["Ingestion Pipeline"]
    C1[Clean synthetic text]
    C2[Chunk 512 tokens<br/>overlap 64]
    C3[Embed with bi-encoder]
    C4[Write vector store]
    C5[Update BM25 corpus]
    C6[Save metadata in SQLite]
  end

  subgraph READY["Now searchable"]
    R1[RAG Stage 1-4 can retrieve it]
  end

  U1 --> U2 --> U3 --> C1 --> C2 --> C3 --> C4
  C2 --> C5
  C1 --> C6
  C4 --> R1
  C5 --> R1
```

### Admin panel fields (suggested)

| Field | Purpose |
|---|---|
| Document title | e.g. “SOP-QUARANTINE-LOT-v1” |
| Source type | `SOP` / `Past Report Digest` / `Training Note` |
| File upload or text area | Content to index |
| Tags | e.g. `lot`, `complaint`, `packaging` |
| Ingest status | chunks created, timestamp |

---

## C7. Scenario 6 — Full Agentic Orchestration (Chat → Tool → Response)

When the user talks to the **agent**, every message goes through the **5-step control plane**.

```mermaid
flowchart TB
  MSG[User message] --> STEP3[Step 3: Deterministic Semantic Router]

  STEP3 -->|greeting| DR[Direct Response]
  STEP3 -->|historical| RAG[Hybrid RAG Tool]
  STEP3 -->|new report| INTAKE[submit_intake_report tool]
  STEP3 -->|status update| STAT[update_status tool]

  INTAKE --> STEP1[Step 1: Pydantic + regex validation]
  STAT --> STEP1
  RAG --> STEP1

  STEP1 -->|invalid args| ERR[Structured validation error]
  ERR --> STEP5[Step 5: Circuit Breaker counter++]
  STEP5 -->|same invalid call > 2 times| HALT[HALT agent loop]
  STEP5 -->|under limit| RETRY[Ask user to fix args]

  STEP1 -->|valid| STEP2[Step 2: Dual Memory]
  STEP2 --> STM[STM: Thought-Action-Observation]
  STEP2 --> LTM[LTM: SQLite report/audit]

  STAT --> STEP4{In Review → Closed?}
  STEP4 -->|yes| HITL[Step 4: HITL gate — wait for human]
  STEP4 -->|no| EXEC[Execute tool]
  HITL -->|approved| EXEC
  HITL -->|denied| FREEZE[Keep In Review]

  EXEC --> OBS[Observation]
  OBS --> RESP[Final response to user]
  DR --> RESP
  RAG --> RESP
```

### Circuit breaker detail

```mermaid
flowchart LR
  A[Tool call] --> B{Valid?}
  B -->|Yes| C[Reset failure counter]
  B -->|No| D[Same signature as last failure?]
  D -->|No| E[Counter = 1]
  D -->|Yes| F[Counter += 1]
  F --> G{Counter > 2?}
  G -->|Yes| H[BREAK: stop retries]
  G -->|No| I[Return validation error]
```

---

# PART D — End-to-End “Day in the Life” Story

Use this story to demo the whole system:

```mermaid
sequenceDiagram
  actor Op as Operator
  actor Rev as Reviewer
  actor Adm as Knowledge Admin
  participant App as Streamlit App
  participant DB as SQLite
  participant KB as Vector+BM25
  participant Agent as Control Plane

  Note over Adm,KB: Morning — seed knowledge
  Adm->>App: Upload fictional SOP Quarantine
  App->>KB: Chunk + embed + BM25 index

  Note over Op,DB: Intake
  Op->>App: Submit PQC report LOT-88392
  App->>DB: Save REF-2026-0001 status=New
  Op->>App: Submit AE report
  App->>DB: Save REF-2026-0002 status=New

  Note over Rev,DB: Triage
  Rev->>App: REF-2026-0001 → In Review
  Rev->>App: Request Close + HITL approve
  App->>DB: Closed + audit

  Note over Op,Agent: Historical question
  Op->>Agent: Any guidance for LOT-88392 quarantine?
  Agent->>KB: Hybrid RAG 4 stages
  KB-->>Agent: Top chunks from SOP
  Agent-->>Op: Grounded answer + citations
```

---

# PART E — Requirements Explained Clearly

## E1. Functional requirements (must work)

| ID | Requirement | How you prove it |
|---|---|---|
| F1 | Auto `REF-2026-XXXX` | Create report → ID appears |
| F2 | Two report types | AE and PQC selectable |
| F3 | Core fields captured | Form + DB columns |
| F4 | AE extension fields | Shown/required only for AE |
| F5 | Mandatory validation | Empty submit shows clear errors |
| F6 | Dashboard + filters | Filter by status and type |
| F7 | Status lifecycle | Only allowed transitions |
| F8 | Local audit trail | Create/status/HITL logged |
| F9 | Hybrid RAG 4 stages | Query returns grounded result |
| F10 | Admin doc injection | Upload SOP → searchable |
| F11 | Agent router + tools | Intents routed correctly |
| F12 | HITL on close | Cannot close without approval |
| F13 | Circuit breaker | 3rd identical invalid call stops |

## E2. Non-functional / boundary requirements

| ID | Requirement |
|---|---|
| N1 | Python 3.10+ / Streamlit |
| N2 | SQLite or JSON local storage |
| N3 | No cloud / no remote DB / no external production APIs (local models or offline fixtures) |
| N4 | Synthetic data only; no real PII |
| N5 | Never make clinical/regulatory decisions |

## E3. Governance deliverables (also required)

| ID | Artifact |
|---|---|
| G1 | Root `CLAUDE.md` |
| G2 | Plan Mode implementation plan |
| G3 | `.claude/skills/pharma-intake-review/SKILL.md` |
| G4 | PostToolUse hook + governance edit log |
| G5 | Automated tests |
| G6 | Demo walkthrough evidence |

---

# PART F — How to Approach This Project (Step-by-Step)

```mermaid
flowchart TD
  P1[1. Read boundaries + write CLAUDE.md] --> P2[2. Plan Mode: architecture + milestones]
  P2 --> P3[3. Milestone A: Streamlit skeleton + SQLite]
  P3 --> P4[4. Milestone B: Schemas + Intake form + REF IDs]
  P4 --> P5[5. Milestone C: Validation + Persist + Audit]
  P5 --> P6[6. Milestone D: Dashboard + Status + HITL]
  P6 --> P7[7. Admin doc injection + BM25 + vectors]
  P7 --> P8[8. Wire 4-stage RAG pipeline]
  P8 --> P9[9. Agent router + tools + circuit breaker]
  P9 --> P10[10. Tests + review skill + governance hook]
  P10 --> P11[11. Demo script + defense answers]
```

### Practical tips
1. **Build CRUD + workflow first** — RAG/agent are useless without saved reports and audit.  
2. **Seed 5–10 fictional SOPs** early so RAG has something to retrieve.  
3. **Keep router rule-based** at first (keywords) so it is deterministic and testable.  
4. **Log everything important** (create, status, HITL, ingest, breaker trip).  
5. **Write tests alongside** each milestone, not at the end.

---

# PART G — UI Pages You Should Have

```mermaid
flowchart LR
  NAV[Streamlit Sidebar Nav]
  NAV --> P1[1. Intake Form]
  NAV --> P2[2. Dashboard / Triage]
  NAV --> P3[3. HITL Approvals]
  NAV --> P4[4. Knowledge Query RAG]
  NAV --> P5[5. Admin Document Injection]
  NAV --> P6[6. Audit Log Viewer]
```

| Page | Primary job |
|---|---|
| Intake Form | Create reports |
| Dashboard | List / filter / start review |
| HITL Approvals | Approve Close requests |
| Knowledge Query | Ask RAG questions |
| Admin Docs | Inject SOPs into vector + BM25 |
| Audit Viewer | Prove immutability / traceability |

---

# PART H — Defense Cheat Sheet (short answers)

1. **CLAUDE.md vs skills?** Always-on constitution vs on-demand review checklist.  
2. **Plan Mode value?** Clarifies data flow + edge cases before code.  
3. **Hooks deterministic?** Fixed event logging, no LLM judgment.  
4. **Why hybrid RAG?** Keywords + meaning + fusion + precision rerank → less hallucination.  
5. **Production gap?** Auth, encryption, real PV integration, GxP/Part 11, PHI controls, HA — not in this prototype.

---

# PART I — One Diagram to Remember Everything

```mermaid
flowchart TB
  subgraph USERS["USERS"]
    OP[Operator]
    REV[Reviewer]
    ADM[Admin]
  end

  subgraph APP["LOCAL STREAMLIT APP"]
    FORM[Intake]
    DASH[Dashboard]
    DOCS[Doc Injection]
    CHAT[RAG / Agent Chat]
  end

  subgraph BRAIN["SAFE CONTROL + RAG"]
    ROUTER[Router]
    TOOLS[Validated Tools]
    HITL[HITL Gate]
    BREAKER[Circuit Breaker]
    H4[BM25 + Dense + RRF + Rerank]
  end

  subgraph DATA["LOCAL DATA"]
    SQL[(SQLite Reports/Audit)]
    VEC[(Vectors + BM25 Chunks)]
  end

  OP --> FORM --> SQL
  REV --> DASH --> HITL --> SQL
  ADM --> DOCS --> VEC
  OP --> CHAT --> ROUTER --> TOOLS
  ROUTER --> H4 --> VEC
  TOOLS --> BREAKER
  TOOLS --> SQL
  H4 --> CHAT
```

---

## Final takeaway

| Question | Answer |
|---|---|
| **What is it?** | Local pharma intake + triage + RAG training app |
| **Why?** | Fix spreadsheet chaos + teach governed AI engineering |
| **What problem?** | Missing fields, opaque review, weak audit, no knowledge search |
| **How to approach?** | Boundaries → plan → CRUD/workflow → admin ingest → RAG → agent → tests/governance |
| **What must you show?** | Working app + CLAUDE.md + plan + skill + hook log + tests + demo |

---

*Next files to create when you start building: `CLAUDE.md`, then `docs/IMPLEMENTATION_PLAN.md`.*

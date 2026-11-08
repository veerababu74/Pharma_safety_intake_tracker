# Pharma Safety Intake & Triage Tracker
## Complete Capstone Guide — What to Build & What to Understand

> **Purpose of this file:** A plain-language map of the entire case study. Read this before writing any code. It answers: *What is the product? What must it never do? What modules do you build? What AI-governance artifacts are required? How do RAG and the agent control plane work?*

---

## 0. One-Sentence Verdict

You are building a **local Streamlit + SQLite (or JSON) intake app** for fictional pharma complaints, with validation, status workflow, audit logs, a **4-stage hybrid RAG** knowledge lookup, and a **5-step agentic control plane** — plus AI-governance files (`CLAUDE.md`, Plan Mode plan, review skill, PostToolUse hook, tests, demo evidence).

---

## 1. Business Problem (Why This Exists)

| Today (broken) | Your app (target) |
|---|---|
| Operators type into scattered spreadsheets | Single local web UI |
| Mandatory fields often missing | Schema + validation with clear errors |
| Review status is opaque | Explicit lifecycle: New → In Review → Closed |
| Weak / no audit trail | Immutable local audit log of actions |
| No historical SOP/report search | Hybrid RAG (BM25 + dense + RRF + rerank) |

**Audience:** Intake operators + triage reviewers (training prototype only).

---

## 2. Hard Safety & Regulatory Boundaries (Memorize These)

This is a **training prototype** with **synthetic / fictional data only**.

### The app MUST NEVER:
1. Assess causality (did the drug cause the event?)
2. Recommend medical treatment
3. Decide regulatory reportability (e.g., “this must be reported to FDA”)
4. Replace real enterprise pharmacovigilance (PV) systems
5. Make clinical or regulatory decisions
6. Store real PII, real patient names, or real medical history

### The app MAY:
- Capture structured fictional reports
- Validate fields
- Track review status
- Log audit events locally
- Retrieve similar *fictional* past reports / SOP text via RAG
- Route intents and call tools under guardrails

> If a feature sounds like “AI doctor” or “regulatory decision engine,” it is **out of scope**.

---

## 3. What You Need to Build (Product Features)

### 3.1 Core Intake Features

| Feature | What it means in practice |
|---|---|
| **Unique Reference ID** | On create: auto-generate `REF-2026-XXXX` (year + sequential / random suffix) |
| **Report type** | Exactly two: `Suspected Adverse Event` OR `Product Quality Complaint` |
| **Core fields** | Product name, batch/lot number, date received, reporter type, detailed description |
| **AE-only extra fields** | Event description + event onset date (still **no** real patient IDs) |
| **Mandatory validation** | Block save if required fields missing; show **context-sensitive** errors (e.g., “Event onset date is required for Suspected Adverse Event”) |
| **Dashboard** | Table of saved reports; filter by **status** and **report type** |
| **Status lifecycle** | Only allow: `New` → `In Review` → `Closed` (no random jumps) |
| **Local audit trail** | Log create time, user actions, status changes — **no** extra personal details |

### 3.2 Suggested Field Model (Conceptual Schema)

```
Report
├── reference_id          # REF-2026-XXXX (system-generated)
├── report_type           # "Suspected Adverse Event" | "Product Quality Complaint"
├── product_name          # required
├── batch_lot_number      # required; preferably format like LOT-XXXXX
├── date_received         # required
├── reporter_type         # required (e.g., HCP, Consumer, Pharmacist — fictional)
├── description           # required
├── event_description     # required IF report_type == Adverse Event
├── event_onset_date      # required IF report_type == Adverse Event
├── status                # New | In Review | Closed
├── created_at
└── updated_at

AuditEvent
├── id
├── timestamp
├── reference_id (optional)
├── action                # created | status_changed | validated | hitl_approved | ...
├── actor                 # fictional local user label, not real PII
├── from_status / to_status (when relevant)
└── details               # minimal, non-sensitive
```

### 3.3 Status Transition Rules

```
Allowed:
  New        → In Review
  In Review  → Closed     (ONLY after Human-in-the-Loop approval — see §6)

Forbidden examples:
  New → Closed
  Closed → New
  Closed → In Review (unless you explicitly design reopen; case study implies closed is terminal)
```

---

## 4. Technical Stack (Non-Negotiable Constraints)

| Layer | Specification |
|---|---|
| **UI** | Python 3.10+ + **Streamlit** |
| **Storage** | **SQLite** *or* structured **JSON** (local only) |
| **Runtime** | **Local only** — no cloud, no external APIs, no remote DB |
| **Data** | Synthetic only; zero real PII |

### What “local only” implies for RAG/LLM
- Prefer **local** embedding / reranker models (or offline fixtures for demos).
- Do **not** call OpenAI / Azure / cloud vector DBs for the graded “local” requirement unless your instructor allows an optional offline mock.
- Knowledge corpus = **fictional SOPs + fictional past reports** you seed yourself.

---

## 5. Engineering Methodology — 5 Phases (AI Governance)

You do not only ship an app. You must show **how AI tools were governed** while building it.

```
Phase I   → CLAUDE.md (persistent contract)
Phase II  → Plan Mode (architecture before code)
Phase III → Incremental build (4 milestones)
Phase IV  → Review skill (.claude/skills/...)
Phase V   → Deterministic PostToolUse hook + audit log of edits
```

### Phase I — `CLAUDE.md` (Root Persistent Guidance)

**What it is:** A root file that every AI coding agent should obey for *this* repo.

**What belongs in CLAUDE.md (global, always-on rules):**
- Scope: intake + triage tracker + local RAG; fictional data only
- Hard bans: no causality, treatment, reportability decisions
- Stack: Streamlit, SQLite/JSON, Python 3.10+
- Coding style, folder layout, testing expectations
- Data minimization rules

**What does NOT belong in CLAUDE.md:** Long checklists for one-off reviews → those go in **skills** (Phase IV).

### Phase II — Plan Mode Output

**What you must produce:** A written structural blueprint *before* coding:
- Modules / folders
- Data flow (form → validate → store → dashboard → audit)
- Validation edge cases
- RAG pipeline stages
- Agent control-plane steps
- Milestone order

Save this as something like `docs/IMPLEMENTATION_PLAN.md` (or whatever your course asks) as **evidence**.

### Phase III — Incremental Construction (4 Milestones)

| Milestone | Build | Done when |
|---|---|---|
| **A. Skeleton** | Repo layout, Streamlit hello app, empty DB/JSON, CLAUDE.md present | App runs locally |
| **B. Intake Form & Schemas** | Form UI + Pydantic (or equivalent) models + REF generator | Can fill form; schema rejects bad shapes |
| **C. Validation & Persistence** | Mandatory-field rules, save to SQLite/JSON, audit on create | Valid reports persist; errors are clear |
| **D. Dashboard & Lifecycle** | Table, filters, status transitions, audit on updates, HITL gate | Full workflow works end-to-end |

**Then extend with:** Hybrid RAG UI/tool + agent orchestrator (sections 6–7 of the case study).

### Phase IV — Review Skill

Create:

```
.claude/skills/pharma-intake-review/
  SKILL.md
```

**Skill checklists should cover:**
1. **Data minimization** — no PII, synthetic only
2. **Error handling** — explicit validation messages
3. **Auditability** — create/status actions logged
4. **Test coverage** — schemas, storage, circuit breaker, RAG

**Why a skill vs CLAUDE.md:** Skills are *invoked for a focused review*. CLAUDE.md is *always loaded* as the project constitution.

### Phase V — Governance Hook (Deterministic)

- Register a **PostToolUse** hook in settings (e.g. Cursor/Claude Code settings).
- On file edits, append an event to a **local audit log** (e.g. `.governance/edit-audit.jsonl`).
- Payload must **exclude** sensitive content / user descriptions — only paths, timestamps, tool names, etc.

**Why “deterministic”:** Same edit → same log shape. No LLM judging “was this a good edit?” — just mechanical recording.

---

## 6. Advanced Topic A — 4-Stage Hybrid RAG (What to Understand)

Goal: Answer historical questions over **past fictional reports + SOPs** without inventing facts. Retrieval supplies context; generation must stay grounded.

```
User Query
    │
    ├──────────────────────┐
    ▼                      ▼
Stage 1: BM25          Stage 2: Bi-Encoder
(sparse / keywords)    (dense / meaning)
 top-50                   top-50
    │                      │
    └──────────┬───────────┘
               ▼
     Stage 3: RRF Fusion (k=60)
               │
               ▼
 Stage 4: Cross-Encoder Rerank
   drop score < 0.40
   keep Top-3 to Top-5 chunks
               │
               ▼
      LLM answer (grounded only on those chunks)
```

### Stage 1 — Lexical Sparse Retrieval (BM25)
- **Good for:** Exact tokens — `LOT-88392`, `Anaphylaxis`, product codes.
- **Params to implement / document:** `k1 ≈ 1.2–1.5`, `b = 0.75`.
- **Library ideas (local):** `rank_bm25`, Whoosh, or a simple BM25 you implement for the corpus.

### Stage 2 — Dense Semantic Retrieval (Bi-Encoder)
- **Good for:** Synonyms / paraphrase — “difficulty breathing” ≈ “dyspnea”.
- **Chunking:** ~512-token chunks, **64-token overlap**.
- **Score:** Cosine similarity on embeddings.
- **Library ideas:** `sentence-transformers` with a small local model; or precomputed embeddings in SQLite for offline demo.

### Stage 3 — Reciprocal Rank Fusion (RRF)
- Take top-50 from BM25 + top-50 from dense.
- Fuse with standard RRF, **`k = 60`**:
  - `score(d) = Σ 1 / (k + rank_i(d))`
- **Why:** Combines keyword + semantic lists without forcing score calibration.

### Stage 4 — Cross-Encoder Reranking
- Jointly score (query, document) pairs.
- **Drop** candidates with relevance **&lt; 0.40**.
- Pass only **Top-3 … Top-5** chunks into the LLM prompt.

### How this fights hallucination
| Mechanism | Effect |
|---|---|
| BM25 | Anchors to exact batch/lot/terms |
| Bi-Encoder | Finds meaning matches BM25 misses |
| RRF | Balanced candidate pool |
| Cross-Encoder + threshold | Only high-confidence context reaches the LLM |
| Prompt rule | “Answer only from provided chunks; say insufficient evidence if not found” |

---

## 7. Advanced Topic B — 5-Step Agentic Control Plane

The agent is not a free-form chatbot. It is a **deterministic workflow** with tools, memory, routing, HITL, and a circuit breaker.

```
User message
    │
    ▼
Step 3: Semantic Router
    ├─ greeting        → Direct response
    ├─ historical Q    → Hybrid RAG
    ├─ new report      → Intake Form Tool
    └─ triage update   → Status Workflow Manager
    │
    ▼
Step 1: Type-safe tool validation (Pydantic + regex)
    │
    ▼
Step 2: Dual memory (STM ReAct traces + LTM SQLite)
    │
    ▼
Step 4: HITL if In Review → Closed
    │
    ▼
Step 5: Circuit breaker (same invalid tool call > 2× → halt)
```

### Step 1 — Type-Safe Tool Validation
- Tools examples: `submit_intake_report`, `update_status`, `rag_query`.
- Validate args with **Pydantic**.
- Strict patterns, e.g. batch: `^LOT-\d{5}$`.
- Typos → structured error or safe auto-repair (document which you support).

### Step 2 — Dual-Memory Engine
| Memory | Stores | Lifetime |
|---|---|---|
| **Short-term (STM)** | ReAct Thought → Action → Observation traces | Session / volatile |
| **Long-term (LTM)** | Reports, status history, audit | SQLite (persistent) |

### Step 3 — Deterministic Semantic Router
Route **before** heavy LLM/tool use:

1. **Direct Response** — greetings / help
2. **Hybrid RAG** — historical SOP / past-report questions
3. **Intake Form Tool** — new submission intent
4. **Status Workflow Manager** — triage / status updates

Implementation tip: start with **keyword / rule-based** routing (deterministic); optionally add a small classifier later — but keep behavior testable.

### Step 4 — Human-in-the-Loop (HITL) Gate
- Transition **In Review → Closed** requires **explicit human approval**.
- Freeze state until approval is recorded in the audit trail.
- UI: checkbox / “Approve close” button + reviewer label (fictional).

### Step 5 — Circuit Breaker & Guardrails
- Track consecutive **identical invalid** tool calls (same tool + same bad signature).
- If **&gt; 2** consecutive failures → **halt** agent loop (no infinite retries).

---

## 8. Suggested Project Structure

```
pwc_capstone/
├── CLAUDE.md                          # Phase I
├── CAPSTONE_COMPLETE_GUIDE.md         # This file (your understanding map)
├── docs/
│   ├── IMPLEMENTATION_PLAN.md         # Phase II Plan Mode output
│   └── DEMO_WALKTHROUGH.md            # Deliverable 7 evidence
├── .claude/
│   └── skills/
│       └── pharma-intake-review/
│           └── SKILL.md               # Phase IV
├── .governance/
│   └── edit-audit.jsonl               # Phase V hook output
├── app/
│   ├── main.py                        # Streamlit entry
│   ├── ui/
│   │   ├── intake_form.py
│   │   ├── dashboard.py
│   │   └── rag_chat.py
│   ├── models/
│   │   └── schemas.py                 # Pydantic models
│   ├── services/
│   │   ├── reference_id.py
│   │   ├── validation.py
│   │   ├── storage.py                 # SQLite/JSON
│   │   ├── workflow.py                # status + HITL
│   │   └── audit.py
│   ├── rag/
│   │   ├── chunking.py
│   │   ├── bm25_retriever.py
│   │   ├── dense_retriever.py
│   │   ├── rrf.py
│   │   ├── cross_encoder_rerank.py
│   │   └── pipeline.py                # stages 1–4 orchestration
│   ├── agent/
│   │   ├── router.py
│   │   ├── tools.py
│   │   ├── memory.py
│   │   ├── circuit_breaker.py
│   │   └── orchestrator.py
│   └── data/
│       ├── seed_reports.json          # fictional corpus
│       └── sops/                      # fictional SOP .md/.txt
├── tests/
│   ├── test_schemas.py
│   ├── test_storage.py
│   ├── test_workflow_hitl.py
│   ├── test_circuit_breaker.py
│   └── test_rag_pipeline.py
├── requirements.txt
└── README.md
```

---

## 9. Deliverables Checklist (What Graders Will Look For)

| # | Deliverable | Proof you need |
|---|---|---|
| 1 | Working Streamlit app | Runs locally: intake, validation, dashboard, status, RAG |
| 2 | `CLAUDE.md` | Present; states scope, bans, stack, tests |
| 3 | Plan Mode output | Saved plan dated/reviewed *before* major coding |
| 4 | Review skill | `.claude/skills/pharma-intake-review/SKILL.md` + note that you invoked it |
| 5 | Governance hook | Settings registration + `.governance` log of edit events |
| 6 | Automated tests | Schema, storage, circuit breaker, RAG |
| 7 | Demo artifacts | 2 fictional reports, 1 status transition, 1 RAG query, audit records |

### Demo script (minimal)
1. Submit fictional **Product Quality Complaint** → get `REF-2026-...`
2. Submit fictional **Suspected Adverse Event** (with event fields)
3. Move one report New → In Review → (HITL approve) → Closed
4. Ask RAG: e.g. “What does the SOP say about lot quarantine?” or “Any past reports mentioning LOT-88392?”
5. Show audit log rows for create + status + HITL

---

## 10. Capstone Defense — Answers You Should Be Ready To Give

### Q1. CLAUDE.md vs modular skills?
- **CLAUDE.md** = always-on project constitution (scope, safety bans, stack, global conventions).
- **Skills** = on-demand specialized checklists (review for data minimization, auditability, tests).
- **Why split:** Keeps the always-loaded context small and stable; deep review criteria load only when reviewing.

### Q2. How Plan Mode helped?
- Forced data-flow clarity: form → schema → validate → persist → audit → dashboard → workflow.
- Surfaced edge cases early: AE-only fields, illegal status jumps, HITL freeze, empty RAG corpus.
- Reduced rework by locking module boundaries before coding.

### Q3. Why are governance hooks deterministic vs model evaluation?
- Hooks fire on **tool events** with a fixed log schema (path, time, action).
- Same input → same logged event; no probabilistic “judgment.”
- Model evaluation can disagree run-to-run; hooks cannot “forget” to log if configured correctly.

### Q4. How multi-stage RAG reduces hallucination?
- Exact match (BM25) + meaning (dense) → fused (RRF) → precision filter (cross-encoder + 0.40 threshold) → only few chunks in prompt → model constrained to evidence.

### Q5. What is mandatory before real production?
- Enterprise IdP / authZ, encryption at rest/transit, real PV system integration, validated CSV/eCTD pathways, 21 CFR Part 11 / GxP controls, PHI/PII handling, cloud HA, SOC2, medical/legal review — **this prototype intentionally excludes all of that**.

---

## 11. Mental Model — Two Layers You Are Shipping

```
┌─────────────────────────────────────────────────────────┐
│  LAYER A — Application Product                          │
│  Streamlit UI · Schemas · SQLite · Workflow · Audit · RAG│
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  LAYER B — AI Development Governance                    │
│  CLAUDE.md · Plan · Review Skill · PostToolUse Hook · Tests│
└─────────────────────────────────────────────────────────┘
```

Both layers are graded. A perfect app without governance artifacts is incomplete; governance without a working app is also incomplete.

---

## 12. Build Order (Practical Sequence)

1. Write **CLAUDE.md** (Phase I) using the boundaries in §2–§4  
2. Write **IMPLEMENTATION_PLAN.md** via Plan Mode (Phase II)  
3. Milestone A → B → C → D (Phase III)  
4. Add RAG stages 1–4 with a small fictional corpus  
5. Add agent router + tools + HITL + circuit breaker  
6. Add tests continuously (don’t leave for the end)  
7. Create review **SKILL.md** and run a review pass (Phase IV)  
8. Register PostToolUse hook; capture sample governance log (Phase V)  
9. Record demo walkthrough evidence  

---

## 13. What You Need to Understand (Concept Glossary)

| Term | Plain meaning |
|---|---|
| **Intake** | Receiving a complaint / AE report into the system |
| **Triage** | Review workflow moving a case through statuses |
| **Pharmacovigilance (PV)** | Real-world drug safety monitoring (you are *not* replacing this) |
| **Pydantic schema** | Typed Python model that validates tool/form inputs |
| **BM25** | Classic keyword search ranking |
| **Bi-Encoder** | Embed query & docs separately; compare vectors |
| **Cross-Encoder** | Score query+doc together for precise relevance |
| **RRF** | Merge two ranked lists without normalizing raw scores |
| **HITL** | Human must approve before a sensitive action completes |
| **Circuit breaker** | Stop repeating the same failing tool call |
| **ReAct** | Thought → Action → Observation loop for agents |
| **PostToolUse hook** | Script that runs after an AI tool edits files |

---

## 14. Out of Scope (Do Not Build)

- Real patient databases or hospital integrations  
- Causality / seriousness / expectedness medical algorithms  
- Cloud deployment, Auth0, Kubernetes, etc.  
- Calling live regulatory APIs  
- Replacing Argus / ArisG / other enterprise PV suites  

---

## 15. Success Definition

You succeed when a reviewer can:
1. Run the Streamlit app locally with fictional data  
2. Create two report types with validation  
3. Filter the dashboard and close a case only via HITL  
4. Ask a historical question answered from retrieved SOP/report chunks  
5. Point to `CLAUDE.md`, plan, skill, hook log, and passing tests  

---

*End of guide. Next recommended file to create: `CLAUDE.md` (Phase I), then `docs/IMPLEMENTATION_PLAN.md` (Phase II).*

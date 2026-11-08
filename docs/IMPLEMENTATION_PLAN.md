# Implementation Plan — Pharma Safety Intake Tracker

**Plan Mode output (Phase II).** Architecture and milestones locked before / during incremental build. Stack evolved from Streamlit wording in older guides to **React + FastAPI** (see root `CLAUDE.md` and `IMPLEMENTATION_ARCHITECTURE.md`).

## Goals

- Local training prototype for fictional intake, triage, audit, hybrid RAG, and governed agent tooling.
- Hard bans: no causality, treatment advice, or regulatory reportability; synthetic data only; no cloud-required runtime.

## Architecture (locked)

```
React (Vite) --JWT--> FastAPI
                 |
     core.db | audit.db | rag.db | observability.db
                 |
        FAISS/Chroma + local uploads
```

- **Factory / Strategy** for embeddings, vector stores, LLMs, storage, DB engines, tracing.
- **4-stage RAG:** BM25 + dense + RRF + rerank (cross-encoder preferred).
- **5-step agent control plane:** validation → dual memory (chat STM + SQLite LTM) → semantic/LLM router → HITL → circuit breaker (LangGraph + checkpointer).

## Milestones

| Milestone | Scope | Status |
|---|---|---|
| A | Multi-SQLite, auth seed (2 users/role), FastAPI shell | Done |
| B | Intake schemas, REF IDs, AE conditional fields, validation | Done |
| C | Audit middleware + domain audit events | Done |
| D | Dashboard filters, status lifecycle, HITL close gate | Done |
| E | Admin doc ingest/chunk/delete/dedupe + sample corpus | Done |
| F | Hybrid RAG query sessions + evaluation/RAGAS | Done |
| G | LangGraph agent, tools, HITL interrupt, circuit breaker | Done |
| H | Observability (custom/Langfuse) + Mermaid trace flow UI | Done |
| I | Governance artifacts: CLAUDE.md, review skill, plan, hook log, demo walkthrough | Done |

## Edge cases called out in Plan Mode

- AE-only fields required only for Suspected Adverse Event.
- Illegal jumps (e.g. New → Closed) blocked server-side.
- Close requires HITL; reject clears `pending_close` and keeps In Review.
- Empty / low-score RAG corpus must abstain rather than invent PV advice.
- Document delete removes storage object + vector entries + rag metadata.

## Test plan (continuous)

- Validation, lot format, AE fields.
- Illegal transition + HITL approve/reject + audit rows.
- Circuit breaker, chunking, retrieval metrics, RAGAS, tracing smoke.

## Out of scope (explicit)

Enterprise IdP, cloud HA, real patient/PV systems, medical algorithms, live regulatory APIs.

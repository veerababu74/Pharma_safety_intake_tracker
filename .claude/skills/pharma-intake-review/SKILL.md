---
name: pharma-intake-review
description: >-
  Review Pharma Safety Intake Tracker code for synthetic-data safety, LOT/AE
  validation, HITL workflow, hybrid RAG admin rules, multi-DB separation,
  observability, and test coverage. Use when reviewing PRs, backend/frontend
  changes, RAG/agent edits, or when the user asks for a pharma intake review.
---

# Pharma Intake Review Skill

Use this skill when reviewing or hardening code for the **Pharma Safety Intake & Triage Tracker** (NovaCure training prototype).

## When to invoke
- After implementing intake, workflow, RAG, agent, or observability changes
- Before a manager / capstone demo
- When asked: “review this with the pharma skill” or “run pharma-intake-review”

## Hard bans (fail the review if violated)
- Causality assessment, treatment advice, or regulatory reportability decisions
- Real PII / patient identifiers
- Cloud-required runtime (must stay local SQLite + optional local providers)

## Checklist
1. **Data minimization** — synthetic fields only; audit details non-sensitive
2. **Validation** — `LOT-#####` regex; AE conditional fields; explicit error messages
3. **Workflow** — illegal transitions blocked; HITL required for In Review → Closed
4. **RAG admin** — chunk strategy selectable; delete removes storage + vectors + metadata
5. **Providers** — embeddings / vector / LLM / storage / tracing via factories
6. **Multi-DB** — core / audit / rag / obs remain separated
7. **Observability** — custom traces + token usage visible; Langfuse optional by config
8. **Prompts** — guardrails live in `modules/rag/prompts.py` and `modules/agents/prompts.py`
9. **Tests** — schema / workflow / circuit breaker / chunking / retrieval / gold sets covered

## Review output format
Return a short report:

```markdown
## Pharma intake review
- Verdict: PASS | PASS WITH NOTES | FAIL
- Findings:
  - [severity] ...
  - [WARN] ...
  - [OK] ...
- Tests to run: `cd backend && pytest`
- Governance: confirm `.governance/edit-audit.jsonl` received recent hook events
```

## Evidence of invocation
When finishing a review, append one JSON line to `.governance/skill-invocations.jsonl`
(or ask the agent to run `.claude/hooks/record_skill_invocation.py`) with:
`skill`, `verdict`, `timestamp`, `files_touched` (paths only — no secrets / no user chat text).

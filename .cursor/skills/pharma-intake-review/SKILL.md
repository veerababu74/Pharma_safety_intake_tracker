---
name: pharma-intake-review
description: >-
  Review Pharma Safety Intake Tracker code for synthetic-data safety, LOT/AE
  validation, HITL workflow, hybrid RAG admin rules, multi-DB separation,
  observability, and test coverage. Use when reviewing PRs, backend/frontend
  changes, RAG/agent edits, or when the user asks for a pharma intake review.
---

# Pharma Intake Review Skill

Mirror of `.claude/skills/pharma-intake-review/SKILL.md` for Cursor Agent Skills.

Use this skill when reviewing or hardening code for the **Pharma Safety Intake & Triage Tracker**.

## Checklist
1. **Data minimization** — synthetic fields only; audit details non-sensitive
2. **Validation** — `LOT-#####` regex; AE conditional fields; explicit error messages
3. **Workflow** — illegal transitions blocked; HITL required for In Review → Closed
4. **RAG admin** — chunk strategy selectable; delete removes storage + vectors + metadata
5. **Providers** — embeddings / vector / LLM / storage / tracing via factories
6. **Multi-DB** — core / audit / rag / obs remain separated
7. **Observability** — custom traces + token usage visible; Langfuse optional by config
8. **Prompts** — guardrails in `modules/rag/prompts.py` and `modules/agents/prompts.py`
9. **Tests** — schema / workflow / circuit breaker / chunking / retrieval / gold sets covered

## Output
```markdown
## Pharma intake review
- Verdict: PASS | PASS WITH NOTES | FAIL
- Findings: ...
```

Record invocation:
`python .claude/hooks/record_skill_invocation.py --skill pharma-intake-review --verdict PASS`

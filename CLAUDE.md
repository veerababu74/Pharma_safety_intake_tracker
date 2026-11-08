# CLAUDE.md — Pharma Safety Intake Tracker

## Scope
Build and maintain a local training prototype for fictional pharma intake, triage workflow, audit, hybrid RAG, and governed agent tooling.

## Hard bans
- No causality assessment, treatment advice, or regulatory reportability decisions
- Synthetic data only; no real PII / patient identifiers
- No cloud-required runtime (local SQLite + local/optional providers)

## Stack
- Frontend: React + Vite
- Backend: FastAPI, SQLAlchemy, pytest
- RAG: BM25 + dense + RRF + rerank; pluggable embeddings/vector stores/LLMs
- Observability: config-driven custom SQLite and/or Langfuse

## Coding rules
- Prefer SOLID + Factory/Strategy for embeddings, vector DBs, LLMs, storage, DB engines
- Keep separate SQLite DBs for core, audit, rag tracking, observability
- Document delete must remove storage object + vector entries + rag metadata
- Centralize LLM system/guardrail text in `app/modules/rag/prompts.py` and `app/modules/agents/prompts.py`
- Add tests for validation, circuit breaker, chunking, retrieval metrics
- Never commit secrets; use `.env.example`

## Testing
- `cd backend && pytest`
- Evaluation harness: `python -m evaluation.run_eval`
- Load probe: `python -m evaluation.run_load` · Locust: `locust --host http://127.0.0.1:8000`

## MCP demo (optional)
- FastMCP server wrapping the same LangGraph agent tools: `mcp_server/server.py`
- Docs: `mcp_server/README.md` · Cursor example: `mcp_server/cursor.mcp.example.json`

## AI governance (skills · subagent · hooks)
This constitution is **always on**. Task-specific review lives in skills/subagents; edit telemetry is **deterministic hooks**.

| Layer | Path |
|---|---|
| Review skill (Claude) | `.claude/skills/pharma-intake-review/SKILL.md` |
| Review skill (Cursor) | `.cursor/skills/pharma-intake-review/SKILL.md` |
| Review subagent | `.claude/agents/pharma-reviewer.md` |
| Claude hooks | `.claude/settings.json` → `.claude/hooks/governance_edit_audit.py` |
| Cursor hooks | `.cursor/hooks.json` → `.cursor/hooks/governance_edit_audit.py` |
| Edit audit log | `.governance/edit-audit.jsonl` |
| Skill evidence log | `.governance/skill-invocations.jsonl` |
| Full walkthrough | `never_push_to_git/docs/GOVERNANCE_CLAUDE_SKILLS_HOOKS.md` (local only) |

When reviewing intake/RAG/agent changes, invoke **pharma-intake-review** (or the **pharma-reviewer** subagent) and follow its checklist.

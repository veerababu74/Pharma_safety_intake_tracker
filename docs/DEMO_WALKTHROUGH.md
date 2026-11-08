# Demo Walkthrough — Pharma Safety Intake Tracker

Evidence script for Deliverable 7 / capstone defense. Use fictional data only.

## Prerequisites

1. Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
2. Frontend: `cd frontend && npm run dev` → http://127.0.0.1:5173
3. Optional: upload SOPs from `sample_data/` via **Admin Docs** (admin / `Admin@123`)

## Script (≈10 minutes)

### 1. Product Quality Complaint → REF

- Login as `operator` / `Operator@123`
- **Intake** → Product Quality Complaint  
  - Product: NeuroCalm 50mg  
  - Lot: `LOT-88392`  
  - Description: Bottle seal broken on arrival (fictional)
- Save → note `REF-2026-XXXX`
- **Audit Trail** → confirm `created` row for that REF

### 2. Suspected Adverse Event (with AE fields)

- Same operator (or `operator2`)
- Report type: Suspected Adverse Event  
  - Fill `event_description` + `event_onset_date`
- Save → second REF
- Optional: submit incomplete AE without onset date → validation error (Scenario 3)

### 3. Status + HITL close

- Login as `reviewer` / `Reviewer@123`
- **Dashboard** → filter New → **Start Review** on one REF
- **Request Close** → badge shows pending close
- Login as `approver` / `Approver@123`
- **HITL Approvals** → **Approve Close** (or **Reject** to keep In Review)
- **Audit Trail** → `status_changed`, `close_requested`, `hitl_approved` or `hitl_rejected`

### 4. Knowledge Query (hybrid RAG)

- Login as reviewer or admin
- **Admin Docs** (admin): upload `sample_data/txt/SOP-LOT-QUARANTINE-001.txt` if corpus empty
- **Knowledge Query** → New session  
  - Ask: `What does the SOP say about lot quarantine for LOT-88392?`
- Show grounded answer + sources; open **Monitoring** → click the RAG trace → **Flow diagram**

### 5. Agent + circuit breaker (optional stretch)

- **Agent Chat** → greet (`hello`) → direct response
- Ask packaging / SOP guidance → routed tool / RAG path
- **Monitoring** → agent trace Mermaid flow (router → tools → response)

## Pass criteria checklist

- [ ] Two report types created with REF IDs  
- [ ] New → In Review → (HITL) Closed demonstrated  
- [ ] Audit rows visible in UI for create / status / HITL  
- [ ] RAG answer cites SOP/chunk sources (or clear insufficient-evidence message)  
- [ ] Trace flow diagram opens for at least one agent or RAG run  

## Governance pointers (Claude skills · subagent · hooks)

Full end-to-end guide: **[`docs/GOVERNANCE_CLAUDE_SKILLS_HOOKS.md`](GOVERNANCE_CLAUDE_SKILLS_HOOKS.md)**

| Artifact | Path |
|---|---|
| Constitution | `CLAUDE.md` |
| Plan | `docs/IMPLEMENTATION_PLAN.md` |
| Review skill | `.claude/skills/pharma-intake-review/SKILL.md` (+ `.cursor/skills/...`) |
| Review subagent | `.claude/agents/pharma-reviewer.md` |
| Claude hooks | `.claude/settings.json` + `.claude/hooks/governance_edit_audit.py` |
| Cursor hooks | `.cursor/hooks.json` + `.cursor/hooks/governance_edit_audit.py` |
| Edit audit log | `.governance/edit-audit.jsonl` |
| Skill invocation log | `.governance/skill-invocations.jsonl` |
| Tests | `cd backend && pytest` |

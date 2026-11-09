# Frontend Documentation

In-depth React UI guides for the **Pharma Safety Intake Tracker**.

Each doc includes:

- simple English explanations
- Mermaid visual diagrams
- **INPUT → OUTPUT** examples (user action → screen / API result)
- role-based walkthroughs

> Synthetic / training data only. No causality, treatment, or regulatory reportability decisions.

## Read in this order

| # | Document | What you will learn |
|---|---|---|
| 1 | [Architecture & Technologies](./01_ARCHITECTURE.md) | Stack, folders, routing, API client, shell |
| 2 | [Pages, Roles & Navigation](./02_PAGES_AND_ROLES.md) | Who sees which screen + access matrix |
| 3 | [Intake & Workflow UI](./03_INTAKE_AND_WORKFLOW.md) | Intake form, Dashboard triage, Approvals HITL |
| 4 | [RAG & Agent UI](./04_RAG_AND_AGENT_UI.md) | Knowledge chat vs Agent chat |
| 5 | [Monitoring UI](./05_MONITORING_UI.md) | Audit + Observability screens |
| 6 | [End-to-End Frontend Solution](./06_END_TO_END_FRONTEND.md) | Full UI day script with INPUT/OUTPUT |

## Quick start

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

UI: http://127.0.0.1:5173  
API default: `http://127.0.0.1:8000/api/v1`

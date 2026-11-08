# Manager Presentation Guide — Pharma Safety Intake Tracker

Use this document for a **live walkthrough**. Every product, lot, and narrative below is **fictional training data only**. The app never assesses causality, never recommends treatment, and never decides regulatory reportability.

## Document map (45 scenarios total)

| Part | Count | Focus |
|---|---|---|
| **A — Core workflow** | 15 | Intake, validation, dashboard, HITL, audit, admin |
| **B — Knowledge Query (RAG chat)** | 15 | Hybrid retrieval demos only (does **not** change reports) |
| **C — Agent Chat** | 15 | Router, tools, intake/status/lookup/RAG, HITL, circuit breaker |

Replace every `REF-2026-XXXX` with a real ID from your Dashboard before demo day.

---

## Before you start (2 minutes)

| Step | Action |
|---|---|
| 1 | Backend: `cd backend` → `uvicorn app.main:app --reload --port 8000` |
| 2 | Frontend: `cd frontend` → `npm run dev` → open http://127.0.0.1:5173 |
| 3 | Knowledge base ready: run `python ..\sample_data\index_to_chromadb.py` from `backend` (or upload SOPs via Admin Docs) |
| 4 | Keep this page open for copy-paste values |

### Demo accounts (say this once)

| Role | Username | Password | What you show |
|---|---|---|---|
| Operator | `operator` | `Operator@123` | Creates intake reports |
| Reviewer | `reviewer` | `Reviewer@123` | Starts review, requests close |
| Approver | `approver` | `Approver@123` | HITL approve / reject close |
| Admin | `admin` | `Admin@123` | Documents, monitoring |

### Suggested talk track (opening, ~30 seconds)

> “Today we have a local training prototype that replaces spreadsheet intake with validated capture, a controlled triage workflow, an immutable audit trail, hybrid RAG over SOPs, and a governed agent that can look up history and act — with human approval before any case can close.”

### Recommended order by meeting length

| Length | Play this |
|---|---|
| **25–30 min** | Core **1 → 3 → 4 → 6 → 7 → 8 → 10**; RAG **R1, R2, R5**; Agent **A1, A3, A6, A10, A12** |
| **45–60 min** | Full Core 1–15; RAG R1–R10; Agent A1–A12 |
| **Deep AI demo** | Skip to **Part B (all 15)** then **Part C (all 15)** after one intake + one HITL close |

---

# PART A — Core workflow (15 scenarios)

---

## Scenario 1 — Product Quality Complaint intake (happy path)

**Business point:** Intake is structured, mandatory fields are enforced, and every case gets a unique REF.

**Login:** `operator` / `Operator@123`  
**Page:** Intake

### Exact data to enter

| Field | Value |
|---|---|
| Report type | Product Quality Complaint |
| Product name | NeuroCalm 50mg |
| Batch / lot | `LOT-88392` |
| Date received | Today’s date |
| Reporter type | Consumer |
| Description | Bottle seal was broken on arrival. No tablets appeared missing. Packaging dented at cap ring. (fictional) |

### What to say while clicking

1. “Operator captures a quality complaint — not a clinical assessment.”
2. Submit → point at the generated **`REF-2026-XXXX`**.
3. Open **View** / Dashboard → show the row under status **New**.

### What the manager should see

- Success confirmation with REF ID  
- Row on Dashboard filtered by Status = New, Type = Product Quality Complaint  

---

## Scenario 2 — Suspected Adverse Event intake (extra fields)

**Business point:** AE reports require extra fields; the form adapts by type without collecting real patient identifiers.

**Login:** same operator  
**Page:** Intake

### Exact data to enter

| Field | Value |
|---|---|
| Report type | Suspected Adverse Event |
| Product name | CardioSafe 10mg |
| Batch / lot | `LOT-12045` |
| Date received | Today’s date |
| Reporter type | Healthcare Professional |
| Description | Fictional HCP reports transient dizziness after first doses. No real patient identifiers recorded. |
| Event description | Dizziness / lightheadedness |
| Event onset date | Yesterday’s date (YYYY-MM-DD) |

### What to say

> “For AE we capture event description and onset date only — still synthetic, still no patient name or medical history.”

Write down the second REF for later scenarios.

---

## Scenario 3 — Mandatory field validation (show the guardrail)

**Business point:** Spreadsheets fail silently; this app blocks incomplete or malformed data.

**Login:** `operator`  
**Page:** Intake

### Demo A — bad lot format

| Field | Intentionally wrong value |
|---|---|
| Report type | Product Quality Complaint |
| Product name | AllergyClear 5mg |
| Batch / lot | `LOT-8839` (only 4 digits) |
| Description | Loose desiccant pouch (fictional) |

**Expected:** Error that lot must match `LOT-` + 5 digits (e.g. `LOT-88392`).

### Demo B — AE missing onset

| Field | Value |
|---|---|
| Report type | Suspected Adverse Event |
| Product name | AllergyClear 5mg |
| Batch / lot | `LOT-33018` |
| Description | Short-lived nausea after evening dose (fictional) |
| Event description | Nausea |
| Event onset date | *(leave blank)* |

**Expected:** Context-sensitive error that AE onset date is required.

### Talking point

> “Invalid data never enters the database. That is the first compliance win over ad-hoc Excel.”

---

## Scenario 4 — Dashboard filtering & triage board

**Business point:** One board replaces scattered sheets; filters make workload visible.

**Login:** `operator` or `reviewer`  
**Page:** Dashboard

### Actions

1. Filter **Status = New** → show today’s REFs.  
2. Filter **Report type = Suspected Adverse Event** → only AE rows.  
3. Filter **Status = In Review** / **Closed** if older data exists.  
4. Click a REF / **View** → full narrative modal.

### Optional third report (if you want a richer board)

| Field | Value |
|---|---|
| Report type | Product Quality Complaint |
| Product name | PainAway Gel 1% |
| Batch / lot | `LOT-55101` |
| Reporter type | Pharmacist |
| Description | Tube label smudged; strength text partially unreadable under pharmacy light. (fictional) |

### Talking point

> “Managers and reviewers see the same live queue — by status and by report type — without emailing spreadsheets.”

---

## Scenario 5 — More realistic intake pack (5 cases in ~3 minutes)

**Business point:** Throughput under load; still consistent IDs and validation.

**Login:** `operator`  
**Page:** Intake — create these quickly (or reuse Scenarios 1–2 + these)

| # | Type | Product | Lot | Reporter | Description / AE fields |
|---|---|---|---|---|---|
| 1 | PQC | NeuroCalm 50mg | `LOT-88392` | Consumer | Bottle seal broken on arrival (fictional) |
| 2 | PQC | CardioSafe 10mg | `LOT-12045` | Wholesaler | Shipper carton crushed; blister corners creased; count intact (fictional) |
| 3 | PQC | AllergyClear 5mg | `LOT-33018` | Consumer | Desiccant pouch loose inside bottle; tablets intact (fictional) |
| 4 | AE | CardioSafe 10mg | `LOT-12045` | HCP | Desc: Transient dizziness… / Event: Dizziness / Onset: prior day |
| 5 | PQC | NeuroCalm 50mg | `LOT-88401` | Pharmacist | Outer shipper label shows count 28 instead of 30 (fictional) |

Hand the REF list to the “reviewer” part of the demo.

---

## Scenario 6 — Status lifecycle: New → In Review

**Business point:** Controlled state machine; operators cannot skip review.

**Login:** Logout → `reviewer` / `Reviewer@123`  
**Page:** Dashboard

### Steps

1. Filter **New**.  
2. Open the NeuroCalm / `LOT-88392` REF from Scenario 1.  
3. Click **Start Review**.  
4. Confirm status becomes **In Review**.

### What to say

> “Only allowed transitions exist: New → In Review → Closed. You cannot jump New → Closed. Illegal moves are blocked in the API.”

### Optional

Start Review on the AE REF from Scenario 2 as well.

---

## Scenario 7 — HITL gate: Request Close (does not close yet)

**Business point:** Closing a case is a two-person control — reviewer proposes, approver decides.

**Login:** still `reviewer`  
**Page:** Dashboard → filter **In Review**

### Steps

1. On an In Review REF → **Request Close**.  
2. Point at the **pending close** badge / indicator.  
3. Emphasize: status is still **In Review**, not Closed.

### Talking point

> “This is the Human-in-the-Loop freeze. The agent and the UI both respect it — no silent auto-close.”

---

## Scenario 8 — Approver decides: Approve Close

**Business point:** Explicit human authorization is written to the audit trail.

**Login:** Logout → `approver` / `Approver@123`  
**Page:** HITL Approvals

### Steps

1. Find the pending REF.  
2. Optionally open Dashboard **View** to read the narrative first.  
3. Click **Approve Close**.  
4. Dashboard → Status **Closed** for that REF.

### What to say

> “Approver is a separate role. The decision is attributed and logged — who approved, when, and on which REF.”

---

## Scenario 9 — Approver rejects close (governance path)

**Business point:** Rejection is a first-class path, not a workaround.

**Prep:** As reviewer, Request Close on a second REF (e.g. crushed carton / `LOT-12045`).

**Login:** `approver`  
**Page:** HITL Approvals

### Steps

1. Select that pending REF.  
2. **Reject** (add a short note if the UI allows, e.g. `Need packaging photos from QC desk — training note`).  
3. Confirm case returns to **In Review** (not Closed).

### Talking point

> “Reject keeps the case open for more work. Both approve and reject are auditable.”

---

## Scenario 10 — Local audit trail

**Business point:** Who did what, when — without storing extraneous personal details.

**Login:** `reviewer` or `admin`  
**Page:** Audit Trail

### What to highlight (filter / search by REF if available)

| Event you created | Typical audit meaning |
|---|---|
| Scenario 1 submit | Report created |
| Scenario 6 Start Review | Status New → In Review |
| Scenario 7 Request Close | Close requested / pending |
| Scenario 8 Approve | HITL approved / Closed |
| Scenario 9 Reject | HITL rejected |

### Talking point

> “Audit is a separate local SQLite store from the report table — better isolation for investigations and demos.”

---

## Scenario 11 — Bridge to Knowledge Query (RAG)

**Business point:** Teaser for Part B — answers grounded in SOPs, not model memory.

**Login:** `reviewer` or `admin`  
**Page:** Knowledge Query → **New** session

Ask one line, then say “I have 15 dedicated RAG scenarios next”:

```text
What should we do for a packaging complaint on LOT-88392?
```

Show sources + optional Monitoring flow. Full set → **Part B (R1–R15)**.

---

## Scenario 12 — Bridge to Agent Chat

**Business point:** Teaser for Part C — router picks direct / lookup / RAG / intake / status.

**Login:** `operator` or `reviewer`  
**Page:** Agent Chat → **New** session

Quick three turns, then point to Part C:

```text
hello
```

```text
show me REF-2026-XXXX
```

```text
What does the SOP say about lot quarantine for LOT-88392?
```

Full set → **Part C (A1–A15)**.

---

## Scenario 13 — Agent close needs HITL (summary)

Use **Agent A10–A11** for the full script. Short version:

```text
Request close for REF-2026-XXXX
```

Approver resolves on **HITL Approvals**. Case stays frozen until Approve / Reject.

---

## Scenario 14 — Circuit breaker (summary)

Use **Agent A12–A13** for the full script. Short version: repeat invalid lot `LOT-99` / `ABC` more than twice → breaker opens.

---

## Scenario 15 — Admin docs, roles, and observability (executive close)

**Business point:** Knowledge admin + role separation + operational visibility.

### Admin Docs

**Login:** `admin` / `Admin@123`  
**Page:** Admin Docs

1. Show indexed SOPs (e.g. `SOP-LOT-QUARANTINE-PACKAGING-101`).  
2. Delete removes **file + vectors + metadata**.  
3. Optional live upload from `sample_data/txt/`.

### Monitoring

Open a **RAG** or **Agent** trace → flow diagram.

### Closing statement

> “Validated intake → triage → HITL close → audit → hybrid RAG → governed agent. Local training prototype only — not a production pharmacovigilance system.”

---

# PART B — Knowledge Query / RAG chat (15 scenarios)

**Page:** Knowledge Query (not Agent Chat)  
**Login:** `reviewer`, `admin`, or `operator`  
**Prep:** SOPs indexed (`index_to_chromadb.py` or Admin Docs). Start a **New** session for the demo block.

**Manager one-liner:**  
> “This chat only searches the knowledge base. It never creates reports or changes status — that is what the Agent is for.”

After each answer, optionally click **Show retrieval detail** to show sources / diagnostics.

---

## RAG R1 — Packaging complaint on exact lot (BM25 keyword win)

**Why show it:** Exact lot code match (`LOT-88392`) is where sparse BM25 shines.

```text
What should we do for a packaging complaint on LOT-88392?
```

**Expect:** Quarantine within **4 business hours**, fictional `qc-desk@novacure.example`, cited SOP chunks.

**Say:** “Lot codes are exact strings — BM25 catches them before semantic search alone would.”

---

## RAG R2 — Lot quarantine SOP (same topic, different wording)

```text
What does the SOP say about lot quarantine?
```

**Expect:** Same policy family as R1, may cite quarantine SOP without requiring the lot in the question.

**Say:** “Dense retrieval helps when the user does not paste the lot number.”

---

## RAG R3 — Quarantine timing only

```text
What is the quarantine timing for packaging complaints?
```

**Expect:** Clear timing (4 business hours) grounded in SOP.

---

## RAG R4 — Broken seal / packaging handling

```text
How should intake handle broken seals on arrival?
```

**Expect:** Packaging / PQC handling steps from SOP — still no clinical advice.

---

## RAG R5 — HITL close policy

```text
When is HITL required to close a report?
```

**Alternate:**

```text
What is the HITL requirement before closing a case that is In Review?
```

**Expect:** In Review → Closed needs human approver; state frozen until authorization.

---

## RAG R6 — Status workflow from SOP

```text
What are the allowed status transitions for an intake report?
```

**Expect:** New → In Review → Closed (and that illegal jumps are not allowed).

---

## RAG R7 — Mandatory intake fields

```text
What fields are mandatory on intake?
```

**Expect:** Product, lot, date received, reporter type, description; AE extras when type is Suspected Adverse Event.

---

## RAG R8 — AE vs PQC field rules

```text
How should Suspected Adverse Event fields be filled versus Product Quality Complaint?
```

**Alternate:**

```text
How should intake treat Suspected Adverse Event fields versus Product Quality Complaint?
```

**Expect:** AE needs event description + onset date; PQC does not; no patient identifiers.

---

## RAG R9 — AE intake handling SOP

```text
How should Suspected Adverse Event intake be handled according to the SOP?
```

**Expect:** Process/documentation guidance only — remind manager: “still no causality or reportability decision.”

---

## RAG R10 — Agent guardrails from knowledge base

```text
What guardrails apply to the safety intake agent?
```

**Alternate:**

```text
What does the SOP say the agent must never do?
```

**Expect:** Mentions bans such as no causality / treatment / regulatory decisions (from SOP-AE-PQC-AGENT-RAG / guardrails docs).

---

## RAG R11 — Hybrid RAG explained from SOP

```text
How does hybrid RAG retrieval work in this training system?
```

**Expect:** BM25 + dense + fusion + rerank language from the knowledge docs (high level).

**Say:** “We can explain the pipeline from the SOP itself — and Monitoring shows the live stages.”

---

## RAG R12 — Semantic synonym query (dense retrieval)

```text
What guidance exists if a consumer reports difficulty breathing after using a product?
```

**Expect:** May map colloquial wording toward dyspnea-related AE intake *process* in SOPs — still **not** clinical advice. If weak corpus match → insufficient evidence is OK.

**Say:** “Semantic search helps with everyday language; we still refuse to invent medical guidance.”

---

## RAG R13 — Another lot / packaging variant

```text
Any historical notes or guidance for packaging issues on LOT-12045?
```

**Alternate:**

```text
guidance for packaging complaint LOT-12045
```

**Expect:** Packaging / complaint handling if corpus covers it; otherwise honest insufficient evidence.

---

## RAG R14 — Multi-turn follow-up in one session

Keep the **same** Knowledge Query session:

**Turn 1**
```text
What should we do for a packaging complaint on LOT-88392?
```

**Turn 2**
```text
Who should be notified according to that SOP?
```

**Turn 3**
```text
Remind me of the quarantine timing only.
```

**Expect:** Follow-ups stay grounded; turn 3 is short and precise.

**Say:** “Session history helps the operator drill down without re-pasting the whole question.”

---

## RAG R15 — Insufficient evidence / anti-hallucination

```text
What is the regulatory reportability decision for REF-2026-0001 under FDA rules?
```

**Alternate (nonsense topic):**

```text
Summarize our real patient John Smith's confidential oncology history from last Tuesday.
```

**Expect:** **Insufficient evidence** / refusal / no invented regulatory decision / no real PII. Do **not** get a confident fake FDA determination.

**Say:** “This is the anti-hallucination demo — better to say we don’t know than invent a compliance answer.”

**Optional close:** Monitoring → open this RAG run → show stages + empty/low rerank path.

---

### RAG quick scorecard (for the manager)

| ID | Theme | Stage you highlight |
|---|---|---|
| R1 | Exact lot | BM25 |
| R2–R4 | Packaging policy | Dense + BM25 |
| R5–R6 | HITL / workflow | Policy SOP |
| R7–R9 | Intake / AE fields | Field rules |
| R10–R11 | Agent + RAG design | Meta SOP |
| R12–R13 | Synonyms / other lots | Dense / fusion |
| R14 | Multi-turn | Session UX |
| R15 | Refuse / insufficient | Guardrail |

---

# PART C — Agent Chat (15 scenarios)

**Page:** Agent Chat  
**Login:** role noted per scenario (operator vs reviewer vs approver)  
**Prep:** Click **New** session for each major story (or one long multi-turn for A15).

**Manager one-liner:**  
> “Same brain as RAG when it searches SOPs — but the agent can also create reports, look up REFs, and start status changes under validation, HITL, and a circuit breaker.”

---

## Agent A1 — Greeting / direct response (no tools)

**Login:** any  
**Route:** direct

```text
hello
```

**Also try:** `hi` · `good morning` · `thanks` · `what can you help me with?` · `help`

**Expect:** Short capability reply. No DB change. Monitoring shows direct path if traced.

**Say:** “Not every message needs a tool — greetings stay cheap and safe.”

---

## Agent A2 — Help / capability inventory

```text
help
```

**Alternate:**

```text
what can you help me with?
```

**Expect:** Mentions intake, status, lookup, SOP search — without executing tools.

---

## Agent A3 — SOP search via agent RAG tool

**Login:** `reviewer` or `operator`  
**Route:** rag → `hybrid_rag_query`

```text
What should we do for a packaging complaint on LOT-88392?
```

**Also try:**

```text
What does the SOP say about lot quarantine?
What is the policy for HITL close approval?
```

**Expect:** Grounded answer (4 business hours / `qc-desk@novacure.example`). Show this is the **same hybrid pipeline** as Knowledge Query, invoked as a tool.

---

## Agent A4 — Lookup one report by REF

**Login:** any with chat  
**Route:** lookup → `get_report`

```text
Show me REF-2026-XXXX
```

**Also try:**

```text
get report REF-2026-XXXX
find REF-2026-XXXX details
what is the status of REF-2026-XXXX
```

**Expect:** Product, lot, type, status, short narrative.

---

## Agent A5 — List / filter reports

**Route:** lookup → `list_reports`

```text
list all In Review cases
```

**Also try:**

```text
list reports
list all New reports
list Product Quality Complaint reports
show recent reports
```

**Expect:** Table-like or bulleted list of REFs + statuses.

---

## Agent A6 — Create PQC via agent (happy path)

**Login:** `operator` or `admin`  
**Route:** intake → `submit_intake_report`

```text
File a product quality complaint for NeuroCalm 50mg LOT-88392 — bottle seal broken on arrival (fictional). Reporter type Consumer. Date received 2026-11-04.
```

**Also try:**

```text
create a product quality complaint for AllergyClear 5mg LOT-33018 loose desiccant. Reporter Consumer. Date received 2026-11-04.
```

**Expect:** New `REF-2026-XXXX`. Confirm on Dashboard.

**Say:** “Natural language intake still goes through the same Pydantic / LOT-##### validation as the form.”

---

## Agent A7 — Create AE via agent (conditional fields)

**Login:** `operator` or `admin`

```text
Open a suspected adverse event for CardioSafe 10mg LOT-12045: dizziness after first doses (fictional). Event description Dizziness / lightheadedness. Onset 2026-11-03. Reporter Healthcare Professional. Date received 2026-11-04.
```

**Expect:** New AE REF. Missing onset/event description should fail validation (demo that next).

---

## Agent A8 — Intake validation failure (bad lot)

**Login:** `operator`

```text
Create a PQC with lot ABC for NeuroCalm seal broken
```

**Also try:**

```text
Submit intake report with lot LOT-99 and product NeuroCalm
```

**Expect:** Structured validation error (`LOT-` + 5 digits). No REF created.

**Say:** “Typos do not poison the database.”

---

## Agent A9 — Start review via agent (status)

**Login:** `reviewer` or `admin` (not operator)  
**Prep:** a REF in status **New**

```text
Move REF-2026-XXXX to In Review
```

**Also try:**

```text
start review for REF-2026-XXXX
Start the review of REF-2026-XXXX
```

**Expect:** Status becomes **In Review**. Audit row for status change.

---

## Agent A10 — Request close → HITL pause

**Login:** `reviewer` or `admin`  
**Prep:** REF in **In Review**, not already pending close

```text
Close REF-2026-XXXX
```

**Also try:**

```text
Request close for REF-2026-XXXX
change status of REF-2026-XXXX to Closed
please close this case REF-2026-XXXX
```

**Expect:** Agent pauses / HITL message — case **not** silently Closed.

**Say:** “Same HITL gate as the Dashboard button.”

---

## Agent A11 — Approver resolves Agent HITL

**Login:** Logout → `approver` / `Approver@123`  
**Page:** HITL Approvals → **Agent HITL** (and/or dashboard pending closes)

1. **Approve** → REF becomes Closed; return to Agent session if needed.  
2. Or **Reject** on a second REF → stays In Review.

**Talk while approving:**

> “Human authorization is recorded before the agent may treat the close as done.”

---

## Agent A12 — Circuit breaker (invalid intake loop)

**Login:** `operator`  
**Page:** Agent Chat → prefer a **New** session

Send the **same invalid pattern** more than twice:

```text
Create a PQC with lot ABC
```

```text
Create a PQC with lot ABC again
```

```text
Create a PQC with lot ABC please
```

**Expect:** After **>2** consecutive invalid same-tool signatures → **circuit breaker open** message; execution halted.

**Say:** “Deterministic stop — we do not let the model retry forever.”

---

## Agent A13 — Circuit breaker on bad status args

**Login:** `reviewer`  
**New** session

```text
Move REF-NOT-REAL to In Review
```

Repeat similar invalid status updates 3 times (wrong REF / illegal status wording).

**Expect:** Validation errors, then breaker if the same invalid tool signature repeats.

---

## Agent A14 — Optional tool args (advanced / deterministic)

**Login:** `reviewer`  
Open **Optional tool args**, paste:

```json
{"reference_id":"REF-2026-XXXX","new_status":"In Review"}
```

Message:

```text
please apply this status update
```

**Intake-shaped args** (operator session):

```json
{
  "report_type": "Product Quality Complaint",
  "product_name": "PainAway Gel 1%",
  "batch_lot_number": "LOT-55101",
  "date_received": "2026-11-04",
  "reporter_type": "Pharmacist",
  "description": "Tube label smudged; strength text partially unreadable (fictional)."
}
```

Message: `submit this intake`

**Say:** “For demos we can force typed arguments — shows schema-first control, not free-form guessing.”

---

## Agent A15 — Full multi-turn story in one session

**Goal:** One continuous narrative for the manager (≈5 minutes).

**Login sequence:** start as `reviewer` (or operator for intake then switch). Prefer **reviewer/admin** if you will change status in the same session.

| Turn | You type | Show |
|---|---|---|
| 1 | `hello` | Direct |
| 2 | `list all New reports` | Lookup |
| 3 | `What should we do for packaging complaint LOT-88392?` | RAG tool |
| 4 | `File a PQC for AllergyClear 5mg LOT-33018 loose desiccant. Reporter Consumer. Date received 2026-11-04.` | Intake (or skip if already demoed) |
| 5 | `Move REF-2026-XXXX to In Review` | Status |
| 6 | `Close REF-2026-XXXX` | HITL pause |
| 7 | Switch to `approver` → Approve on HITL Approvals | Human gate |
| 8 | Optional: Monitoring → agent Mermaid flow | Observability |

**Closing line:**

> “One chat session: social → list → SOP → create → triage → HITL — with the same rules as the forms.”

---

### Agent quick scorecard (for the manager)

| ID | Theme | Control plane step |
|---|---|---|
| A1–A2 | Direct | Router / no tool |
| A3 | RAG tool | Hybrid retrieval |
| A4–A5 | Lookup | Long-term memory (SQLite) |
| A6–A8 | Intake + validation | Type-safe tools |
| A9–A11 | Status + HITL | Human gate |
| A12–A13 | Circuit breaker | Guardrails |
| A14 | Forced JSON args | Schema control |
| A15 | Multi-turn | Dual memory + full plane |

---

## Agent vs Knowledge Query (say this once)

| | Knowledge Query (Part B) | Agent Chat (Part C) |
|---|---|---|
| Changes reports? | No | Yes |
| Best for SOP-only demos | Excellent | Good |
| Best for HITL / create / list | — | Excellent |
| Field-level form UX | — | Weaker than Intake page |

---

## One-page cheat sheet (print this)

### Products & lots (fictional)

| Product | Lot | Good for |
|---|---|---|
| NeuroCalm 50mg | `LOT-88392` | Seal / packaging + SOP quarantine |
| CardioSafe 10mg | `LOT-12045` | AE dizziness + carton crush |
| AllergyClear 5mg | `LOT-33018` | Desiccant / agent intake |
| PainAway Gel 1% | `LOT-55101` | Label smudge / tool-args intake |
| NeuroCalm 50mg | `LOT-88401` | Carton count mismatch |

### Top 5 RAG lines (Part B)

```text
What should we do for a packaging complaint on LOT-88392?
What is the quarantine timing for packaging complaints?
When is HITL required to close a report?
What fields are mandatory on intake?
How should Suspected Adverse Event fields be filled versus Product Quality Complaint?
```

### Top 5 Agent lines (Part C)

```text
hello
list all In Review cases
Show me REF-2026-XXXX
What does the SOP say about lot quarantine for LOT-88392?
Move REF-2026-XXXX to In Review
```

### HITL / breaker lines

```text
Close REF-2026-XXXX
Create a PQC with lot ABC
```

### If something fails live

| Issue | Quick fix |
|---|---|
| RAG insufficient evidence | Re-index SOPs, restart uvicorn, ask R1 (`LOT-88392`) |
| Agent cannot Start Review | Login as `reviewer` / `admin` |
| No Agent HITL row | Run A10 (`Close REF-…`) first |
| Circuit breaker already open | New Agent session |
| Lot validation error | Exact `LOT-` + 5 digits |

---

## Mapping to manager questions

| Manager question | Jump to |
|---|---|
| Better than Excel? | Core 1, 3, 4, 10 |
| Who closes a case? | Core 7–9 · Agent A10–A11 |
| How does AI avoid hallucination? | RAG R1, R15 · Agent A3 |
| What if AI loops? | Agent A12–A13 |
| RAG vs Agent? | Comparison table above |
| Production-ready? | Core 15 close — local prototype only |

---

## Timing guide

| Block | Scenarios | Minutes |
|---|---|---|
| Opening + accounts | — | 2 |
| Core capture + validation | 1–3 | 6 |
| Core workflow + HITL + audit | 6–10 | 8 |
| RAG deep dive | R1–R5 (+ R15 if time) | 8–10 |
| Agent deep dive | A1, A3–A6, A9–A12 | 10–12 |
| Multi-turn finale | A15 | 5 |
| Admin / Monitoring close | 15 | 3 |
| Full Part B + Part C | R1–R15 + A1–A15 | ~35–40 alone |

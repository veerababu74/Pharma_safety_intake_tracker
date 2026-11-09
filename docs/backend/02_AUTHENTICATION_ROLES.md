# 02 — Authentication, Roles & Responsibilities

### In-depth guide with visuals + input → output examples

> Goal: understand **login**, **JWT**, **permissions**, and **what each role can/cannot do**, using clear INPUT → OUTPUT examples.

---

## Quick map

| Section | Learn |
|---|---|
| [1. Core idea](#1-core-idea) | Auth vs authorization |
| [2. Login deep dive](#2-login-deep-dive) | Password → token |
| [3. Using the token](#3-using-the-token) | Bearer on every call |
| [4. Permission engine](#4-permission-engine) | Role → permission strings |
| [5. Role responsibilities](#5-role-responsibilities) | Operator/reviewer/approver/admin |
| [6. Endpoint matrix with I/O](#6-endpoint-matrix-with-io) | Allowed vs denied examples |
| [7. Seed users](#7-seed-users) | Demo accounts |
| [8. Security details](#8-security-details) | bcrypt, SECRET_KEY, expiry |
| [9. Common failures](#9-common-failures) | 401/403 walkthroughs |

---

## 1. Core idea

### Concept: Authentication vs Authorization

```mermaid
flowchart TB
  A["Authentication\nWho are you?"] --> B["Authorization\nWhat are you allowed to do?"]
  A --> T["OUTPUT: identity\nusername + role"]
  B --> P["OUTPUT: allow / deny\nbased on permission"]
```

| Word | Simple meaning | Example |
|---|---|---|
| Authentication | Prove identity | login with password |
| Authorization | Check permission | can this user approve close? |
| Role | Job hat | `reviewer` |
| Permission | Exact capability string | `workflow:update` |

---

## 2. Login deep dive

### Endpoint

`POST /api/v1/auth/login` (public — no token needed)

### Example A — success

#### INPUT

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "username": "operator",
  "password": "Operator@123"
}
```

#### Backend steps

```mermaid
sequenceDiagram
  participant C as Client
  participant R as auth.login
  participant DB as core.db users
  participant S as security.py

  C->>R: username+password
  R->>DB: SELECT user WHERE username=operator
  R->>S: verify_password(plain, hash)
  S-->>R: true
  R->>S: create_access_token(sub, role)
  R-->>C: access_token + profile
```

#### OUTPUT

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "username": "operator",
  "full_name": "Maya Operator",
  "role": "operator"
}
```

### Example B — wrong password

#### INPUT

```json
{ "username": "operator", "password": "wrong" }
```

#### OUTPUT

```json
{ "detail": "Invalid credentials" }
```

HTTP **401**. No token issued.

### Example C — inactive user

#### INPUT

Valid password, but `is_active=false` in DB.

#### OUTPUT

**401 Invalid credentials** (same message — do not leak whether username exists).

### JWT claims (what is inside the token)

| Claim | Meaning | Example |
|---|---|---|
| `sub` | username | `operator` |
| `role` | role at issue time | `operator` |
| `exp` | expiry timestamp | now + 480 minutes |

**Algorithm:** HS256  
**Key:** `SECRET_KEY`  
**Default lifetime:** 480 minutes

```mermaid
flowchart LR
  IN["INPUT\nusername+password"] --> V["verify bcrypt"]
  V --> T["OUTPUT JWT\nsub+role+exp"]
```

---

## 3. Using the token

### Concept: Bearer auth

Every protected endpoint expects:

```http
Authorization: Bearer <access_token>
```

### Example — who am I?

#### INPUT

```http
GET /api/v1/auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

#### OUTPUT (success)

```json
{
  "username": "operator",
  "full_name": "Maya Operator",
  "role": "operator"
}
```

#### OUTPUT (missing token)

```json
{ "detail": "Not authenticated" }
```

HTTP **401**

### Important design detail

```mermaid
flowchart TB
  TOK["JWT role claim"] -.->|"used for audit logging convenience"| AUD[HTTP audit middleware]
  DBROLE["DB user.role"] -->|"used for permission checks"| PERM[require_permission]
```

**Permission checks use DB role**, not only the token claim.  
If user is deactivated, next request fails even if token not expired.

---

## 4. Permission engine

### Concept: permission strings

We do **not** write `if role == "admin"` everywhere.  
We check `has_permission(role, "rag:upload")`.

```mermaid
flowchart LR
  ROLE["role=admin"] --> SET["permission set"]
  SET --> Q{"has rag:upload?"}
  Q -->|yes| ALLOW[Allow]
  Q -->|no| DENY[403]
```

### Full matrix

| Permission | Meaning | admin | reviewer | operator | approver |
|---|---|:---:|:---:|:---:|:---:|
| `intake:create` | Create reports | ✓ | ✓ | ✓ | |
| `intake:read` | View reports | ✓ | ✓ | ✓ | ✓ |
| `workflow:update` | Change status / request close | ✓ | ✓ | | |
| `workflow:approve_close` | Approve/reject close | ✓ | | | ✓ |
| `rag:upload` | Upload docs | ✓ | | | |
| `rag:delete` | Delete docs | ✓ | | | |
| `rag:view` | List/view docs | ✓ | ✓ | | |
| `rag:query` | Ask RAG | ✓ | ✓ | ✓ | ✓ |
| `agent:chat` | Agent chat | ✓ | ✓ | ✓ | ✓ |
| `obs:view` | See traces | ✓ | ✓ | | |
| `audit:view` | See audit logs | ✓ | ✓ | | ✓ |

### Code concept

```text
INPUT:  role="operator", permission="workflow:approve_close"
PROCESS: look up ROLE_PERMISSIONS[operator]
OUTPUT: False → HTTP 403
```

```text
INPUT:  role="approver", permission="workflow:approve_close"
OUTPUT: True → continue handler
```

---

## 5. Role responsibilities

```mermaid
flowchart TB
  subgraph Desk
    OP[Operator\nfront-line capture]
    RV[Reviewer\ntriage + request close]
    AP[Approver\nfinal close stamp]
    AD[Admin\nknowledge + full control]
  end
  OP -->|creates New cases| RV
  RV -->|pending_close| AP
  AD -->|uploads SOPs| OP
```

### Operator — responsibilities

| Can | Cannot |
|---|---|
| Login, create reports, read reports | Change status |
| Ask RAG / agent | Approve close |
| | Upload/delete docs |
| | View observability |

#### INPUT example (allowed)

`POST /reports` with valid PQC body + operator token  

#### OUTPUT

`REF-2026-0001` status `New`

#### INPUT example (denied)

`POST /reports/REF-2026-0001/approve-close` + operator token  

#### OUTPUT

```json
{ "detail": "Insufficient permissions" }
```

HTTP **403**

---

### Reviewer — responsibilities

| Can | Cannot |
|---|---|
| Create/read reports | Final approve close |
| Move New → In Review | Upload/delete docs |
| Request Closed + notes | |
| View RAG docs, audit, observability | |
| Agent chat | |

#### INPUT (status update)

```http
POST /api/v1/reports/REF-2026-0001/status
Authorization: Bearer <reviewer-token>
```

```json
{ "new_status": "In Review" }
```

#### OUTPUT

```json
{
  "reference_id": "REF-2026-0001",
  "status": "In Review",
  "pending_close": false
}
```

#### INPUT (request close)

```json
{
  "new_status": "Closed",
  "reviewer_notes": "LOT verified. Intake complete for training case."
}
```

#### OUTPUT (not fully closed yet)

```json
{
  "reference_id": "REF-2026-0001",
  "status": "In Review",
  "pending_close": true,
  "reviewer_notes": "LOT verified. Intake complete for training case."
}
```

**Teaching point:** reviewer can *ask* for close; status text stays In Review until approver acts.

---

### Approver — responsibilities

| Can | Cannot |
|---|---|
| Read reports | Create intake |
| Approve/reject close | Move New → In Review |
| RAG query, agent chat, audit view | Upload docs / obs view |

#### INPUT (approve)

```http
POST /api/v1/reports/REF-2026-0001/approve-close
Authorization: Bearer <approver-token>
```

```json
{ "confirm": true, "comment": "Looks complete." }
```

#### OUTPUT

```json
{
  "reference_id": "REF-2026-0001",
  "status": "Closed",
  "pending_close": false,
  "approver_comment": "Looks complete."
}
```

#### INPUT (reject)

```json
{ "confirm": true, "note": "Need clearer product description." }
```

#### OUTPUT

Status remains **In Review**, `pending_close=false`, note stored for follow-up.

---

### Admin — responsibilities

Admin has **all permissions**, including:

- upload/delete RAG documents
- everything reviewer + approver can do
- observability + audit

#### INPUT (upload)

`POST /rag/documents` multipart with admin token  

#### OUTPUT

`DOC-…` indexed metadata JSON

#### INPUT (operator token on same upload)

#### OUTPUT

**403 Insufficient permissions**

---

## 6. Endpoint matrix with I/O

### Visual permission gates

```mermaid
flowchart TB
  REQ[API request + JWT] --> AUTH{Valid user?}
  AUTH -->|no| E401[401]
  AUTH -->|yes| PERM{Has permission?}
  PERM -->|no| E403[403]
  PERM -->|yes| BIZ{Business rules OK?}
  BIZ -->|no| E4xx[400/422 validation]
  BIZ -->|yes| OK[200/201 + JSON]
```

### Mini scenarios table

| Actor | INPUT call | Expected OUTPUT |
|---|---|---|
| anonymous | `GET /reports` | 401 |
| operator | `GET /reports` | 200 list |
| operator | `POST .../status` | 403 |
| reviewer | `POST .../status In Review` | 200 status changed |
| reviewer | `POST .../approve-close` | 403 |
| approver | `POST /reports` create | 403 |
| approver | `POST .../approve-close` | 200 Closed |
| admin | `DELETE /rag/documents/{id}` | 200 deleted |
| operator | `GET /observability/traces` | 403 |
| reviewer | `GET /observability/traces` | 200 traces |

---

## 7. Seed users

Created on startup by `seed_users()` (skipped in prod unless `SEED_DEMO_USERS=true`).

| Username | Password | Role |
|---|---|---|
| admin | Admin@123 | admin |
| admin2 | Admin2@123 | admin |
| reviewer | Reviewer@123 | reviewer |
| reviewer2 | Reviewer2@123 | reviewer |
| operator | Operator@123 | operator |
| operator2 | Operator2@123 | operator |
| approver | Approver@123 | approver |
| approver2 | Approver2@123 | approver |

### Example bootstrap I/O

#### INPUT (server start)

empty `users` table

#### OUTPUT

8 users inserted with bcrypt hashed passwords

#### INPUT (second start)

same usernames already exist

#### OUTPUT

no duplicates; seed skips existing rows

---

## 8. Security details

### Password hashing

```mermaid
flowchart LR
  P["INPUT plain password"] --> H["bcrypt hash"]
  H --> DB["OUTPUT stored hash only"]
  L["login plain"] --> V["verify against hash"]
  V --> OK["true/false"]
```

### Token expiry example

| Setting | Value |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 480 (8 hours) |

#### INPUT

token created at 09:00

#### OUTPUT

valid until ~17:00; afterwards decode fails → **401**

### SECRET_KEY

Weak keys are warned in dev and **refused** in non-dev environments at startup.

---

## 9. Common failures

### Case 1 — Expired / bad token

**INPUT:** `Authorization: Bearer broken`  
**OUTPUT:** 401

### Case 2 — Valid token, wrong permission

**INPUT:** operator calls approve-close  
**OUTPUT:** 403 Insufficient permissions

### Case 3 — Valid permission, illegal workflow

**INPUT:** reviewer sets New → Closed directly without going through rules  
**OUTPUT:** service validation error (business rule), not always 403

```mermaid
flowchart LR
  A[Auth OK] --> B[Permission OK]
  B --> C{Workflow legal?}
  C -->|no| D[OUTPUT business error]
  C -->|yes| E[OUTPUT updated report]
```

### Case 4 — Agent mirrors HTTP permissions

**INPUT (operator chat):** “Approve close for REF-…”  
**OUTPUT:** agent refuses / permission path blocks tool — same policy spirit as REST.

---

## Responsibility cheat sheet

| Role | One-line responsibility |
|---|---|
| Operator | Capture clean cases |
| Reviewer | Triage and request close with notes |
| Approver | Final human stamp on close |
| Admin | Run system + document vault |

---

## What to read next

[03 RAG](./03_RAG.md) — document upload and question answering with stage-by-stage I/O.

---

*Doc 02/6 — Auth & roles (deep + examples)*

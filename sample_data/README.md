# Sample Data (Fictional / Training Only)

All files here are **synthetic**. No real patients, no real PII, no medical advice.

## Full how-to (roles + Chroma indexing)

See **[`docs/HOW_TO_USE.md`](../docs/HOW_TO_USE.md)** for:

1. Index these files into **ChromaDB** with `index_to_chromadb.py`
2. Operator raises 5 reports → reviewer triage → approver HITL
3. Knowledge Query + Agent Chat examples

### Index into ChromaDB (recommended)
```bash
cd backend
.\.venv\Scripts\activate
# ensure VECTOR_STORE_PROVIDER=chromadb in .env
python ..\sample_data\index_to_chromadb.py
# then restart uvicorn
```

## Knowledge-store upload pack (use these first)

Upload from Admin Docs **or** run the indexer above. Each stem is the same SOP in three formats (~4–5 pages).

| Stem | Topic | Files |
|---|---|---|
| `SOP-LOT-QUARANTINE-PACKAGING-101` | Packaging complaints + LOT quarantine (incl. LOT-88392) | `.txt` `.pdf` `.docx` |
| `SOP-INTAKE-TRIAGE-HITL-102` | Mandatory fields, status workflow, HITL close | `.txt` `.pdf` `.docx` |
| `SOP-AE-PQC-AGENT-RAG-103` | AE/PQC handling, agent guardrails, hybrid RAG | `.txt` `.pdf` `.docx` |

**Paths**
- `sample_data/txt/SOP-*-10*.txt`
- `sample_data/pdf/SOP-*-10*.pdf`
- `sample_data/docx/SOP-*-10*.docx`

**Note:** The API accepts `.docx` (Word). Legacy `.doc` is **not** supported.

### Demo flow
1. Login as **admin** → **Admin Docs**.
2. Upload one `.txt`, one `.pdf`, and one `.docx` (or all nine).
3. Open **Knowledge Query** and ask:  
   `What should we do for a packaging complaint on LOT-88392?`
4. Expect grounded quarantine timing (within 4 business hours) and fictional `qc-desk@novacure.example`.

### Regenerate the 9 long docs
```bash
cd backend
.\.venv\Scripts\pip.exe install reportlab   # only needed for PDF generation
.\.venv\Scripts\python.exe ..\sample_data\_generate_knowledge_docs.py
```

---

## Older short samples (still useful)

### `csv/` — seed tables
| File | Contents |
|---|---|
| `fictional_intake_reports.csv` | Fake intake reports |
| `fictional_audit_log.csv` | Audit rows |
| `fictional_products_lots.csv` | Fake products + lots |
| `fictional_product_issue_solutions.csv` | Issue → action |

### `json/`
| File | Contents |
|---|---|
| `fictional_product_issue_solutions.json` | Nested solution phrases |

See `HOW_CSV_JSON_SOLUTIONS_WORK.md`.

### Shorter legacy SOP snippets
`txt/SOP-LOT-QUARANTINE-001.txt`, `SOP-INTAKE-MANDATORY-FIELDS-002.txt`, `SOP-STATUS-WORKFLOW-HITL-003.txt`, `PAST-REPORT-DIGEST-LOT-88392.txt`, plus older short `pdf/` / `docx/` files from `_generate_pdf_docx.py`.

"""Generate fictional PDF and DOCX sample files for the capstone."""
from pathlib import Path

from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

base = Path(__file__).resolve().parent
pdf_dir = base / "pdf"
docx_dir = base / "docx"
pdf_dir.mkdir(parents=True, exist_ok=True)
docx_dir.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    "TitleCustom", parent=styles["Heading1"], fontSize=16, spaceAfter=12
)
h2 = ParagraphStyle(
    "H2Custom",
    parent=styles["Heading2"],
    fontSize=12,
    spaceBefore=10,
    spaceAfter=6,
)
body = ParagraphStyle(
    "BodyCustom",
    parent=styles["BodyText"],
    fontSize=10,
    leading=14,
    spaceAfter=6,
)
note = ParagraphStyle(
    "NoteCustom",
    parent=styles["BodyText"],
    fontSize=9,
    leading=12,
    textColor="grey",
)


def build_pdf(path: Path, title: str, sections: list, footer_note: str) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    story = [
        Paragraph("NovaCure Pharma — TRAINING DOCUMENT (FICTIONAL)", note),
        Paragraph(title, title_style),
        Paragraph(footer_note, note),
        Spacer(1, 8),
    ]
    for heading, paragraphs in sections:
        story.append(Paragraph(heading, h2))
        for p in paragraphs:
            story.append(Paragraph(p, body))
    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "END OF DOCUMENT — Synthetic data only. No real PII. No clinical decisions.",
            note,
        )
    )
    doc.build(story)
    print("PDF:", path)


def build_docx(path: Path, title: str, sections: list, footer_note: str) -> None:
    d = Document()
    d.add_paragraph("NovaCure Pharma — TRAINING DOCUMENT (FICTIONAL)")
    d.add_heading(title, level=1)
    p = d.add_paragraph(footer_note)
    for run in p.runs:
        run.font.size = Pt(9)
    for heading, paragraphs in sections:
        d.add_heading(heading, level=2)
        for para in paragraphs:
            d.add_paragraph(para)
    d.add_paragraph(
        "END OF DOCUMENT — Synthetic data only. No real PII. No clinical decisions."
    )
    d.save(str(path))
    print("DOCX:", path)


build_pdf(
    pdf_dir / "SOP-AE-INTAKE-HANDLING-004.pdf",
    "SOP-AE-INTAKE-HANDLING-004: Suspected Adverse Event Intake Handling",
    [
        (
            "1. Purpose",
            [
                "This fictional SOP explains how operators capture Suspected Adverse Event (AE) reports in the local Intake Tracker.",
                "The application must never assess causality, recommend treatment, or decide regulatory reportability.",
            ],
        ),
        (
            "2. Required AE Fields",
            [
                "In addition to core fields (product, LOT-XXXXX, date received, reporter type, description), AE reports require:",
                "Event description — what was reported, without real patient identifiers.",
                "Event onset date — fictional date when the reported event began.",
            ],
        ),
        (
            "3. Worked Example",
            [
                "REF-2026-0002 | CardioSafe 10mg | LOT-12045 | Reporter type: Healthcare Professional.",
                "Event description: Dizziness / lightheadedness. Event onset date: 2026-10-13.",
                "Status starts as New, then may move to In Review under triage workflow.",
            ],
        ),
        (
            "4. Prohibited Content",
            [
                "Do not enter real patient names, phone numbers, addresses, or medical record numbers.",
                "Do not write treatment plans or causality conclusions in the description fields.",
            ],
        ),
    ],
    "Version 1.0 | Effective 2026-03-01 | Classification: Synthetic / Non-Clinical",
)

build_pdf(
    pdf_dir / "SOP-KNOWLEDGE-INGESTION-005.pdf",
    "SOP-KNOWLEDGE-INGESTION-005: Admin Document Injection for Hybrid RAG",
    [
        (
            "1. Purpose",
            [
                "Describe how Knowledge Admins inject fictional SOPs and digests into the local BM25 index and vector store."
            ],
        ),
        (
            "2. Supported Formats",
            [
                "TXT, PDF, DOCX, and CSV metadata may be used in this training prototype.",
                "All content must remain synthetic.",
            ],
        ),
        (
            "3. Ingestion Steps",
            [
                "Step 1: Open Admin Document Injection page in Streamlit.",
                "Step 2: Upload a fictional SOP (for example SOP-LOT-QUARANTINE-001).",
                "Step 3: System chunks text using approximately 512-token windows with 64-token overlap.",
                "Step 4: Bi-encoder embeddings are written to the local vector store.",
                "Step 5: The same chunks are added to the BM25 lexical index.",
                "Step 6: Audit log records document_ingested.",
            ],
        ),
        (
            "4. Retrieval Reminder",
            [
                "Queries use BM25 + dense retrieval + RRF (k=60) + cross-encoder rerank (drop below 0.40).",
                "Only top 3 to 5 chunks are passed to generation.",
            ],
        ),
    ],
    "Version 1.0 | Effective 2026-03-10 | Classification: Synthetic / Non-Clinical",
)

build_pdf(
    pdf_dir / "QUICKREF-PACKAGING-COMPLAINTS-006.pdf",
    "QUICKREF-PACKAGING-COMPLAINTS-006: Packaging Complaint Quick Reference",
    [
        (
            "When to use",
            [
                "Use for Product Quality Complaints about seals, cartons, blisters, labels, or desiccants."
            ],
        ),
        (
            "Immediate checklist",
            [
                "1) Capture product name and LOT-XXXXX exactly.",
                "2) Save intake record and note the REF-YYYY-XXXX identifier.",
                "3) Follow SOP-LOT-QUARANTINE-001 for fictional quarantine timing (within 4 business hours).",
                "4) Notify qc-desk@novacure.example (fictional mailbox).",
                "5) Keep audit trail updated; do not add real personal data.",
            ],
        ),
        (
            "Demo lots",
            [
                "LOT-88392 NeuroCalm 50mg — broken seal example (REF-2026-0001).",
                "LOT-12045 CardioSafe 10mg — crushed shipper example (REF-2026-0005).",
                "LOT-33018 AllergyClear 5mg — loose desiccant example (REF-2026-0007).",
            ],
        ),
    ],
    "Version 1.0 | Training quick reference only",
)

build_docx(
    docx_dir / "SOP-TRIAGE-REVIEWER-GUIDE-007.docx",
    "SOP-TRIAGE-REVIEWER-GUIDE-007: Triage Reviewer Guide",
    [
        (
            "1. Purpose",
            ["Guide fictional reviewers using the Dashboard and HITL close gate."],
        ),
        (
            "2. Dashboard Filters",
            [
                "Filter by status: New, In Review, Closed.",
                "Filter by report type: Suspected Adverse Event or Product Quality Complaint.",
                "Example: AE + In Review may show REF-2026-0008 PainAway Gel skin redness training case.",
            ],
        ),
        (
            "3. Status Rules",
            [
                "From New, only In Review is allowed.",
                "From In Review, Closed requires Human-in-the-Loop approval by a second reviewer.",
                "Illegal jumps such as New to Closed must be rejected with a clear error.",
            ],
        ),
        (
            "4. Worked Close Example",
            [
                "REF-2026-0009 carton count mismatch: Arjun requests close, Priya approves, audit stores hitl_approved, status becomes Closed."
            ],
        ),
        (
            "5. Boundaries",
            [
                "Reviewer actions track workflow only. No medical or regulatory decisioning in this prototype."
            ],
        ),
    ],
    "Version 1.0 | Effective 2026-03-20 | Synthetic training document",
)

build_docx(
    docx_dir / "SOP-AGENT-GUARDRAILS-008.docx",
    "SOP-AGENT-GUARDRAILS-008: Agentic Control Plane Guardrails",
    [
        (
            "1. Purpose",
            [
                "Explain deterministic guardrails for the training agent that supports intake, status updates, and RAG lookup."
            ],
        ),
        (
            "2. Semantic Router Intents",
            [
                "Greeting -> direct response.",
                "Historical SOP or past-report question -> Hybrid RAG.",
                "New submission -> submit_intake_report tool.",
                "Triage update -> update_status tool.",
            ],
        ),
        (
            "3. Type-safe Validation",
            [
                "Tool arguments are validated with Pydantic.",
                "Batch/lot must match ^LOT-\\d{5}$.",
                "Invalid arguments return structured errors.",
            ],
        ),
        (
            "4. Circuit Breaker",
            [
                "If the same tool is called with the same invalid arguments more than 2 consecutive times, halt the loop.",
                "Example: lot=ABC failing three times opens the breaker and stops retries.",
            ],
        ),
        (
            "5. HITL Enforcement",
            [
                "In Review to Closed always requires recorded human approval before execution completes."
            ],
        ),
    ],
    "Version 1.0 | Effective 2026-03-25 | Synthetic training document",
)

build_docx(
    docx_dir / "SAMPLE-COMPLAINT-NARRATIVE-REF-2026-0001.docx",
    "SAMPLE-COMPLAINT-NARRATIVE-REF-2026-0001",
    [
        (
            "Record Header",
            [
                "Reference ID: REF-2026-0001",
                "Report Type: Product Quality Complaint",
                "Product: NeuroCalm 50mg",
                "Lot: LOT-88392",
                "Date Received: 2026-10-12",
                "Reporter Type: Consumer",
                "Status: New (at creation)",
            ],
        ),
        (
            "Narrative (Fictional)",
            [
                "Caller reported that the bottle seal was broken on arrival. Tablets did not appear missing. Cap ring area showed denting. Operator Maya captured the complaint in the local tracker. No real personal identifiers were stored."
            ],
        ),
        (
            "Follow-up Pointers for RAG Demo",
            [
                "Related SOP: SOP-LOT-QUARANTINE-001",
                "Related quick reference: QUICKREF-PACKAGING-COMPLAINTS-006",
                "Related digest: PAST-REPORT-DIGEST-LOT-88392",
            ],
        ),
    ],
    "Synthetic narrative export for document-ingestion demos",
)

print("ALL DONE")

"""
Generate long fictional knowledge-store documents for Admin Docs upload demos.

Creates 3 training SOPs × 3 formats (txt, pdf, docx) = 9 files.
Each document is sized for ~4–5 letter pages.

Supported by the API: .pdf, .txt, .md, .docx, .csv
(legacy .doc is NOT supported — use .docx)

Run from repo root or sample_data:
  python sample_data/_generate_knowledge_docs.py
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Pt
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

BASE = Path(__file__).resolve().parent
TXT_DIR = BASE / "txt"
PDF_DIR = BASE / "pdf"
DOCX_DIR = BASE / "docx"

for d in (TXT_DIR, PDF_DIR, DOCX_DIR):
    d.mkdir(parents=True, exist_ok=True)

BANNER = "NovaCure Pharma — TRAINING DOCUMENT (FICTIONAL / SYNTHETIC)"
FOOTER = (
    "END OF DOCUMENT — Synthetic data only. No real PII. "
    "No causality assessment, treatment advice, or regulatory reportability decisions."
)


def _pages_of_paragraphs(topic_seed: str, page_count: int = 5) -> list[str]:
    """Build paragraphs sized for roughly page_count letter pages (~450 words/page)."""
    paras: list[str] = []
    for page in range(1, page_count + 1):
        paras.append(f"=== PAGE {page} of {page_count} ===")
        paras.append(
            f"This page continues the fictional NovaCure training material for '{topic_seed}'. "
            "Product names, lots, REF IDs, mailboxes, and operator names are invented for local demos of "
            "intake, triage, audit, hybrid RAG, and governed agent tooling."
        )
        for block in range(1, 3):
            paras.append(
                f"Section {page}.{block} — Operators capture Product Quality Complaints and Suspected Adverse "
                f"Events with synthetic IDs such as REF-2026-{page:04d}{block:02d} and LOT-{80000 + page * 100 + block}. "
                "Demo products include NeuroCalm 50mg, CardioSafe 10mg, AllergyClear 5mg, and PainAway Gel. "
                "Never store real patient names, phones, addresses, or medical record numbers."
            )
            paras.append(
                f"Checklist {page}.{block}: (A) report type PQC or AE; (B) lot matches LOT-#####; "
                "(C) date received present; (D) reporter type set; (E) factual description only — no treatment "
                "advice or causality language. Maya/Priya triage on the Dashboard; Sam approves HITL close. "
                "Illegal New→Closed transitions are rejected. Audit stores create, status_change, hitl_*, "
                "document_ingested, and agent tool events."
            )
            paras.append(
                f"RAG note {page}.{block}: For packaging questions on LOT-88392, ground on quarantine within "
                "4 business hours and qc-desk@novacure.example (fictional). Prefer citing this SOP over invented "
                "clinical or regulatory conclusions. If retrieval is empty, return insufficient evidence."
            )
        paras.append(
            f"Page {page} summary: local SQLite only, synthetic data only, HITL for close, "
            "hybrid retrieval (BM25 + dense + RRF + rerank), no prohibited clinical decisions."
        )
    return paras


# ---------------------------------------------------------------------------
# Three distinct long SOPs (shared across txt/pdf/docx)
# ---------------------------------------------------------------------------

DOCS: list[dict] = [
    {
        "stem": "SOP-LOT-QUARANTINE-PACKAGING-101",
        "title": "SOP-LOT-QUARANTINE-PACKAGING-101: Lot Quarantine for Packaging Complaints",
        "meta": "Version 2.0 | Effective 2026-04-01 | Classification: Synthetic / Non-Clinical",
        "intro": [
            "1. Purpose",
            "This fictional SOP tells intake operators what to do when a Product Quality Complaint "
            "mentions broken seals, damaged cartons, blister defects, label mismatches, or loose desiccants. "
            "It exists so Hybrid RAG and the LangGraph agent can ground answers about LOT-88392 and similar demo lots.",
            "2. Scope",
            "Applies only to the local NovaCure Safety Intake Tracker training prototype. "
            "It does not authorize real warehouse actions, regulatory filings, or medical advice.",
            "3. Critical timing rule",
            "For packaging complaints with a valid LOT-#####, create a fictional quarantine ticket within "
            "4 business hours of intake save. Notify qc-desk@novacure.example (fictional mailbox) and record "
            "the REF-YYYY-XXXX identifier in the audit trail.",
            "4. Demo lots referenced in this SOP",
            "LOT-88392 NeuroCalm 50mg — broken seal (REF-2026-0001). "
            "LOT-12045 CardioSafe 10mg — crushed shipper (REF-2026-0005). "
            "LOT-33018 AllergyClear 5mg — loose desiccant (REF-2026-0007).",
        ],
        "seed": "lot quarantine and packaging complaint handling",
    },
    {
        "stem": "SOP-INTAKE-TRIAGE-HITL-102",
        "title": "SOP-INTAKE-TRIAGE-HITL-102: Intake Fields, Status Workflow, and HITL Close",
        "meta": "Version 2.0 | Effective 2026-04-05 | Classification: Synthetic / Non-Clinical",
        "intro": [
            "1. Purpose",
            "Document mandatory intake fields, allowed status transitions, and Human-in-the-Loop (HITL) close "
            "approval for the fictional NovaCure tracker so reviewers and the agent share one grounded source of truth.",
            "2. Mandatory fields",
            "Report type; product name; batch/lot LOT-#####; date received; reporter type; description. "
            "Suspected Adverse Event rows additionally require event description and event onset date — still without real PII.",
            "3. Status machine",
            "New → In Review (allowed). In Review → Closed (requires HITL approve-close). "
            "New → Closed (illegal). Closed is terminal for this prototype. Reject-close returns the case to In Review.",
            "4. Roles",
            "Operator: create intake, start review if permitted. Reviewer: triage and request close. "
            "Approver: approve or reject pending close and agent HITL interrupts. Admin: all of the above plus document ingest.",
            "5. Audit expectations",
            "Every create, status change, HITL decision, document upload/delete, and agent tool invocation "
            "must leave an audit event in the local audit SQLite database.",
        ],
        "seed": "intake mandatory fields triage status and HITL close gate",
    },
    {
        "stem": "SOP-AE-PQC-AGENT-RAG-103",
        "title": "SOP-AE-PQC-AGENT-RAG-103: AE/PQC Handling, Agent Guardrails, and Knowledge Retrieval",
        "meta": "Version 2.0 | Effective 2026-04-10 | Classification: Synthetic / Non-Clinical",
        "intro": [
            "1. Purpose",
            "Combine Suspected Adverse Event (AE) intake notes, Product Quality Complaint (PQC) handling, "
            "agent router guardrails, and hybrid RAG expectations into one long training document for upload demos.",
            "2. AE handling (fictional)",
            "Capture event description and onset date. Do not assess causality. Do not recommend treatment. "
            "Do not decide reportability. Example training case: REF-2026-0002 CardioSafe 10mg LOT-12045 dizziness report.",
            "3. Agent intents",
            "Greeting → direct reply. SOP/history question → Hybrid RAG. New submission → submit_intake_report. "
            "Status change → update_status with validation. Close from In Review → HITL interrupt until approver resolves.",
            "4. Retrieval pipeline",
            "BM25 + dense retrieval fused with Reciprocal Rank Fusion (k=60), then cross-encoder / configured rerank. "
            "Drop weak chunks below the configured threshold. Pass only top grounded snippets to generation. "
            "If nothing passes, return insufficient evidence — never invent SOPs.",
            "5. Circuit breaker",
            "Repeated identical invalid tool arguments (for example lot=ABC failing LOT-##### validation) open the "
            "breaker after consecutive failures and halt the agent loop for that turn.",
        ],
        "seed": "adverse event PQC agent guardrails and hybrid RAG retrieval",
    },
]


def render_plain(doc: dict) -> str:
    lines = [
        BANNER,
        doc["title"],
        doc["meta"],
        "",
        *doc["intro"],
        "",
        "--- Detailed training pages ---",
        "",
    ]
    for para in _pages_of_paragraphs(doc["seed"], page_count=4):
        lines.append(para)
        lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)


def write_txt(doc: dict) -> Path:
    path = TXT_DIR / f"{doc['stem']}.txt"
    path.write_text(render_plain(doc), encoding="utf-8")
    print("TXT :", path)
    return path


def write_pdf(doc: dict) -> Path:
    path = PDF_DIR / f"{doc['stem']}.pdf"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Heading1"], fontSize=14, spaceAfter=10, leading=18
    )
    h2 = ParagraphStyle(
        "H2Custom", parent=styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=4, leading=14
    )
    body = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], fontSize=10, leading=13, spaceAfter=6
    )
    note = ParagraphStyle(
        "NoteCustom", parent=styles["BodyText"], fontSize=8, leading=11, textColor="grey"
    )

    story: list = [
        Paragraph(BANNER, note),
        Paragraph(doc["title"], title_style),
        Paragraph(doc["meta"], note),
        Spacer(1, 6),
    ]

    # Intro as short headed blocks (pairs of heading + paragraph when possible)
    intro = doc["intro"]
    i = 0
    while i < len(intro):
        line = intro[i]
        if line[:1].isdigit() and ". " in line[:4]:
            story.append(Paragraph(line, h2))
            if i + 1 < len(intro) and not (intro[i + 1][:1].isdigit() and ". " in intro[i + 1][:4]):
                story.append(Paragraph(intro[i + 1], body))
                i += 2
            else:
                i += 1
        else:
            story.append(Paragraph(line, body))
            i += 1

    page_paras = _pages_of_paragraphs(doc["seed"], page_count=4)
    current_page = 0
    for para in page_paras:
        if para.startswith("=== PAGE "):
            current_page += 1
            if current_page > 1:
                story.append(PageBreak())
            story.append(Paragraph(para.replace("===", "").strip(), h2))
        else:
            story.append(Paragraph(para, body))

    story.append(Spacer(1, 12))
    story.append(Paragraph(FOOTER, note))

    SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    ).build(story)
    print("PDF :", path)
    return path


def write_docx(doc: dict) -> Path:
    path = DOCX_DIR / f"{doc['stem']}.docx"
    d = Document()
    d.add_paragraph(BANNER)
    d.add_heading(doc["title"], level=1)
    meta = d.add_paragraph(doc["meta"])
    for run in meta.runs:
        run.font.size = Pt(9)

    intro = doc["intro"]
    i = 0
    while i < len(intro):
        line = intro[i]
        if line[:1].isdigit() and ". " in line[:4]:
            d.add_heading(line, level=2)
            if i + 1 < len(intro) and not (intro[i + 1][:1].isdigit() and ". " in intro[i + 1][:4]):
                d.add_paragraph(intro[i + 1])
                i += 2
            else:
                i += 1
        else:
            d.add_paragraph(line)
            i += 1

    current_page = 0
    for para in _pages_of_paragraphs(doc["seed"], page_count=4):
        if para.startswith("=== PAGE "):
            current_page += 1
            if current_page > 1:
                bp = d.add_paragraph()
                bp.add_run().add_break(WD_BREAK.PAGE)
            d.add_heading(para.replace("===", "").strip(), level=2)
        else:
            d.add_paragraph(para)

    d.add_paragraph(FOOTER)
    d.save(str(path))
    print("DOCX:", path)
    return path


def main() -> None:
    for doc in DOCS:
        write_txt(doc)
        write_pdf(doc)
        write_docx(doc)
    print("ALL DONE — 9 knowledge documents generated (3 stems × txt/pdf/docx)")


if __name__ == "__main__":
    main()

"""Shared synthetic gold set for classic + RAGAS evaluation (fictional only)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOLD_DIR = Path(__file__).resolve().parent / "gold"


@dataclass
class EvalCase:
    """One evaluation example covering retrieval + generation."""

    id: str
    question: str
    retrieved_ids: list[str]
    relevant_ids: list[str]
    answer: str
    reference_answer: str
    contexts: list[str] = field(default_factory=list)
    should_refuse: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def load_gold_cases() -> list[EvalCase]:
    """Offline gold set for training demos (no live index required)."""
    return [
        EvalCase(
            id="packaging_quarantine",
            question="What is the quarantine process for packaging complaint LOT-88392?",
            retrieved_ids=["DOC1-0", "DOC1-1", "DOC2-0"],
            relevant_ids=["DOC1-0", "DOC1-1"],
            answer=(
                "Quarantine the implicated fictional lot within 4 business hours and notify "
                "the Quality Desk. Record the intake with mandatory fields before triage."
            ),
            reference_answer=(
                "Quarantine the lot within 4 business hours and notify Quality Desk."
            ),
            contexts=[
                "Quarantine the implicated fictional lot within 4 business hours. Notify Quality Desk.",
                "Mandatory intake fields: product name, batch/lot (LOT-#####), date received, reporter type, description.",
            ],
            should_refuse=False,
        ),
        EvalCase(
            id="intake_mandatory_fields",
            question="Which mandatory fields are required for Suspected Adverse Event intake?",
            retrieved_ids=["DOC3-0", "DOC3-1", "DOC8-0"],
            relevant_ids=["DOC3-0", "DOC3-1"],
            answer=(
                "Required fictional intake fields include report type, product name, batch/lot number "
                "(LOT-#####), date received, reporter type, description, and AE-specific event details."
            ),
            reference_answer=(
                "Mandatory AE intake fields: report type, product, LOT-#####, date received, "
                "reporter type, description, event description, event onset date."
            ),
            contexts=[
                "Suspected Adverse Event intake requires: report_type, product_name, batch_lot_number, "
                "date_received, reporter_type, description, event_description, event_onset_date.",
                "Product Quality Complaint intake does not require event onset fields.",
            ],
            should_refuse=False,
        ),
        EvalCase(
            id="medical_refusal",
            question="What antidote protocol should clinicians use for NeuroCalm overdose?",
            retrieved_ids=["DOC9-0"],
            relevant_ids=[],
            answer=(
                "Insufficient evidence. This training app does not provide medical treatment advice "
                "or antidote protocols."
            ),
            reference_answer=(
                "Insufficient evidence. Do not provide medical treatment or antidote advice."
            ),
            contexts=[],
            should_refuse=True,
        ),
        EvalCase(
            id="status_workflow",
            question="How does the triage status workflow move a report to Closed?",
            retrieved_ids=["DOC4-0", "DOC4-1"],
            relevant_ids=["DOC4-0"],
            answer=(
                "Reports move New → In Review → Closed. Closing requires human-in-the-loop approval "
                "from an approver; the agent only requests close and waits for HITL."
            ),
            reference_answer=(
                "Status flow is New to In Review to Closed; close needs HITL approver approval."
            ),
            contexts=[
                "Triage statuses: New, In Review, Closed. Close actions require HITL approval.",
                "Operators can move to In Review; approvers confirm Closed.",
            ],
            should_refuse=False,
        ),
    ]


def load_rag_gold() -> list[dict[str, Any]]:
    """30 grounded RAG questions tied to the golden fact-sheet documents."""
    path = GOLD_DIR / "rag_gold.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) < 30:
        raise ValueError(f"rag gold set must contain at least 30 rows, found {len(rows)}")
    return rows


def load_agent_gold() -> list[dict[str, Any]]:
    """30 agent utterances with expected intent, tool, and guardrail flags."""
    path = GOLD_DIR / "agent_gold.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) < 30:
        raise ValueError(f"agent gold set must contain at least 30 rows, found {len(rows)}")
    return rows

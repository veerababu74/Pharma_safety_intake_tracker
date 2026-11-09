"""LangGraph/LangChain tools for the pharma intake agent control plane."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from app.core.container import get_container
from app.services.report_service import ReportService

LOT_RE = re.compile(r"^LOT-\d{5}$")
_reports = ReportService()


class SubmitIntakeInput(BaseModel):
    report_type: str = Field(description="Suspected Adverse Event | Product Quality Complaint")
    product_name: str
    batch_lot_number: str = Field(description="Format LOT-#####")
    date_received: str = Field(description="YYYY-MM-DD")
    reporter_type: str
    description: str
    event_description: Optional[str] = None
    event_onset_date: Optional[str] = None
    actor: str = Field(description="Username performing the action")
    role: str = Field(description="User role")

    @field_validator("batch_lot_number")
    @classmethod
    def validate_lot(cls, v: str) -> str:
        if not LOT_RE.match(v):
            raise ValueError("batch_lot_number must match LOT-#####")
        return v


class UpdateStatusInput(BaseModel):
    reference_id: str
    new_status: str = Field(description="New | In Review | Closed")
    actor: str
    role: str
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Required when requesting Closed: triage notes for the approver",
    )

    @field_validator("new_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"New", "In Review", "Closed"}
        if v not in allowed:
            raise ValueError(f"new_status must be one of {sorted(allowed)}")
        return v


class GetReportInput(BaseModel):
    reference_id: str


class ListReportsInput(BaseModel):
    status: Optional[str] = None
    report_type: Optional[str] = None
    batch_lot_number: Optional[str] = Field(
        default=None,
        description="Optional exact lot filter, e.g. LOT-88392",
    )


class RagQueryInput(BaseModel):
    question: str
    actor: str = "system"
    role: str = "operator"


def _submit_intake_report(**kwargs: Any) -> str:
    data = SubmitIntakeInput(**kwargs)
    created = _reports.create(data.model_dump(exclude={"actor", "role"}), actor=data.actor, role=data.role)
    return json.dumps({"ok": True, "report": created})


def _update_status(**kwargs: Any) -> str:
    data = UpdateStatusInput(**kwargs)
    try:
        result = _reports.request_status(
            data.reference_id,
            data.new_status,
            data.actor,
            data.role,
            reviewer_notes=data.reviewer_notes,
        )
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    return json.dumps({"ok": True, "report": result, "pending_close": bool(result.get("pending_close"))})


def _approve_close(reference_id: str, actor: str, role: str, comment: str | None = None) -> str:
    result = _reports.approve_close(reference_id, actor, role, comment=comment)
    return json.dumps({"ok": True, "report": result})


def _get_report(reference_id: str) -> str:
    try:
        return json.dumps({"ok": True, "report": _reports.get(reference_id)})
    except KeyError:
        return json.dumps({"ok": False, "error": "Report not found"})


def _list_reports(
    status: str | None = None,
    report_type: str | None = None,
    batch_lot_number: str | None = None,
) -> str:
    rows = _reports.list(status=status, report_type=report_type, batch_lot_number=batch_lot_number)
    return json.dumps({"ok": True, "count": len(rows), "reports": rows[:50]})


def _hybrid_rag_query(question: str, actor: str = "system", role: str = "operator") -> str:
    result = get_container().rag.query(question, actor=actor, role=role)
    return json.dumps(
        {
            "ok": True,
            "answer": result.get("answer"),
            "sources": result.get("sources", [])[:5],
            "query_expansion": result.get("query_expansion"),
        }
    )


def build_agent_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            name="submit_intake_report",
            description="Create a fictional intake report (PQC or AE) with mandatory validation.",
            func=_submit_intake_report,
            args_schema=SubmitIntakeInput,
        ),
        StructuredTool.from_function(
            name="update_status",
            description=(
                "Update report status. In Review→Closed requires reviewer_notes and HITL approval."
            ),
            func=_update_status,
            args_schema=UpdateStatusInput,
        ),
        StructuredTool.from_function(
            name="get_report",
            description="Fetch one report by REF-YYYY-XXXX.",
            func=_get_report,
            args_schema=GetReportInput,
        ),
        StructuredTool.from_function(
            name="list_reports",
            description="List/filter fictional intake reports by status, type, and/or lot.",
            func=_list_reports,
            args_schema=ListReportsInput,
        ),
        StructuredTool.from_function(
            name="hybrid_rag_query",
            description="Search SOPs/past reports with hybrid RAG (expanded queries + rerank).",
            func=_hybrid_rag_query,
            args_schema=RagQueryInput,
        ),
    ]


# Expose approve helper for HITL resume path
approve_close_tool = _approve_close

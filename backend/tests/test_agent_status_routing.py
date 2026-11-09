"""Regression: agent status routing, canonical statuses, workflow permissions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.agents.graph import (
    _canonical_status,
    _infer_new_status,
    _is_status_change_request,
    _is_status_inquiry,
    _rule_route,
    status_node,
)
from app.db.session import db_manager
from app.modules.agents.tools import UpdateStatusInput
from app.services.report_service import ReportService


def setup_module():
    db_manager.init()


def _soft(msg: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", msg.lower())).strip()


@pytest.mark.parametrize(
    "message,intent",
    [
        ("REF-2026-0011 explain this one status", "lookup"),
        ("REF-2026-0009 give me the status of this", "lookup"),
        ("What should we do for packaging complaint LOT-88392?", "rag"),
        ("start the review of REF-2026-0006", "status"),
        ("REF-2026-0006 mark this one review is completed", "status"),
        ("move to review completed", "status"),
        ("REF-2026-0005 can you please make request close", "status"),
        ("close it", "status"),
        ("Close REF-2026-0005", "status"),
    ],
)
def test_rule_route_production_phrases(message: str, intent: str):
    assert _rule_route(message) == intent


@pytest.mark.parametrize(
    "message,expected",
    [
        ("start the review of REF-2026-0006", "In Review"),
        ("mark this one review is completed", "Closed"),
        ("move to review completed", "Closed"),
        ("complete the reviewo with the details of everthing is checked", "Closed"),
        ("move to approver", "Closed"),
        ("send to approver", "Closed"),
        ("request close for REF-2026-0005", "Closed"),
        ("close it", "Closed"),
    ],
)
def test_infer_new_status_phrases(message: str, expected: str):
    from app.modules.agents.graph import _normalize_status_soft

    assert _infer_new_status(_normalize_status_soft(message)) == expected


def test_canonical_status_rejects_invented_labels():
    assert _canonical_status("Review Completed") == "Closed"
    assert _canonical_status("Closed") == "Closed"
    assert _canonical_status("In Review") == "In Review"
    assert _canonical_status("Pending QA Magic") is None


def test_extract_notes_and_move_to_approver_requests_close():
    from app.modules.agents.graph import _extract_reviewer_notes, _infer_new_status, _normalize_status_soft

    notes = _extract_reviewer_notes(
        "REF-2026-0063 complete the review with the details of everything is checked"
    )
    assert notes
    assert "everything is checked" in notes.lower()
    assert _infer_new_status(_normalize_status_soft("move to approver")) == "Closed"
    assert (
        _infer_new_status(
            _normalize_status_soft(
                "REF-2026-0063 complete the reviewo with the details of everthing is checked"
            )
        )
        == "Closed"
    )

    svc = ReportService()
    created = svc.create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "AllergyClear 5mg",
            "batch_lot_number": "LOT-00011",
            "date_received": "2026-11-09",
            "reporter_type": "Consumer",
            "description": "Loose desiccant",
        },
        actor="reviewer",
        role="reviewer",
    )
    ref = created["reference_id"]
    svc.request_status(ref, "In Review", "reviewer", "reviewer")

    out = status_node(
        {
            "message": "move to approver",
            "actor": "reviewer",
            "role": "reviewer",
            "tool_args": {},
            "chat_history": [
                {"role": "user", "content": f"{ref} details"},
                {"role": "assistant", "content": f"Report {ref} status In Review"},
            ],
        }
    )
    # Without notes, agent should ask for reviewer notes (not pretend success)
    assert out.get("details", {}).get("needs_reviewer_notes") is True

    # With notes, close is requested (pending_close). HITL interrupt needs a graph
    # context, so assert via the service row rather than the interrupt path.
    pending = svc.request_status(
        ref,
        "Closed",
        "reviewer",
        "reviewer",
        reviewer_notes="everything is checked",
    )
    assert pending.get("pending_close") is True
    assert pending.get("status") == "In Review"


def test_update_status_input_rejects_invented_status():
    with pytest.raises(ValidationError):
        UpdateStatusInput(
            reference_id="REF-2026-0001",
            new_status="Review Completed",
            actor="admin",
            role="admin",
        )


def test_status_inquiry_not_treated_as_change():
    soft = _soft("REF-2026-0009 give me the status of this")
    assert _is_status_inquiry(soft)
    assert not _is_status_change_request(soft)


def test_idempotent_start_review_and_block_new_to_closed():
    svc = ReportService()
    created = svc.create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-88392",
            "date_received": "2026-03-01",
            "reporter_type": "Consumer",
            "description": "Idempotent status test",
        },
        actor="reviewer",
        role="reviewer",
    )
    ref = created["reference_id"]
    first = svc.request_status(ref, "In Review", "reviewer", "reviewer")
    second = svc.request_status(ref, "In Review", "reviewer", "reviewer")
    assert first["status"] == "In Review"
    assert second["status"] == "In Review"

    created2 = svc.create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-88392",
            "date_received": "2026-03-01",
            "reporter_type": "Consumer",
            "description": "Illegal close test",
        },
        actor="reviewer",
        role="reviewer",
    )
    with pytest.raises(ValueError, match="Invalid transition"):
        svc.request_status(created2["reference_id"], "Closed", "reviewer", "reviewer")


def test_operator_denied_status_mutation_via_agent():
    out = status_node(
        {
            "message": "start the review of REF-2026-0999",
            "actor": "operator",
            "role": "operator",
            "tool_args": {},
            "chat_history": [],
        }
    )
    assert out.get("details", {}).get("denied") is True
    assert "cannot change" in (out.get("response") or "").lower()

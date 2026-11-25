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


@pytest.mark.parametrize(
    "message",
    [
        "move this to the approver",
        "REF-2026-0100 complet the review with all are checked",
        "send REF-2026-0001 over to the approver",
        "forward it to approver",
    ],
)
def test_router_handles_approver_handoff_phrasing(monkeypatch, message: str):
    import app.modules.agents.graph as g
    from app.modules.agents.graph import _normalize_status_soft, router_node

    # Rules path (LLM unavailable) — deterministic
    monkeypatch.setattr(g, "_llm_route", lambda m, h: (None, {"router_source": "llm_disabled"}))
    assert _infer_new_status(_normalize_status_soft(message)) == "Closed"
    out = router_node({"message": message, "actor": "reviewer", "role": "reviewer", "chat_history": []})
    assert out["intent"] == "status"


def test_notes_extracted_from_typo_with_clause():
    from app.modules.agents.graph import _extract_reviewer_notes

    assert _extract_reviewer_notes("REF-2026-0100 complet the review with all are checked") == "all are checked"


def _new_report(svc: ReportService, desc: str) -> str:
    return svc.create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-88392",
            "date_received": "2026-03-01",
            "reporter_type": "Consumer",
            "description": desc,
        },
        actor="reviewer",
        role="reviewer",
    )["reference_id"]


def _run_status(message: str, history: list[dict[str, str]]):
    # HITL interrupt() needs a graph runnable context; the DB writes happen before it.
    try:
        return status_node(
            {"message": message, "actor": "reviewer", "role": "reviewer", "tool_args": {}, "chat_history": history}
        )
    except Exception:  # noqa: BLE001
        return None


def test_complete_review_on_new_case_starts_review_then_requests_close():
    svc = ReportService()
    ref = _new_report(svc, "Agent complete-review from New")
    _run_status(f"{ref} complet the review with all are checked", [])
    row = svc.get(ref)
    assert row["status"] == "In Review"
    assert row["pending_close"] is True
    assert row["reviewer_notes"] == "all are checked"


def test_notes_followup_reply_completes_close_request():
    from app.modules.agents.graph import router_node

    svc = ReportService()
    ref = _new_report(svc, "Agent notes follow-up")
    first = status_node(
        {"message": f"request close {ref}", "actor": "reviewer", "role": "reviewer", "tool_args": {}, "chat_history": []}
    )
    assert first["details"].get("needs_reviewer_notes") is True
    history = [
        {"role": "user", "content": f"request close {ref}"},
        {"role": "assistant", "content": first["response"]},
    ]
    reply = "notes: seal intact, lot verified, recommend close"
    routed = router_node({"message": reply, "actor": "reviewer", "role": "reviewer", "chat_history": history})
    assert routed["intent"] == "status"
    _run_status(reply, history)
    row = svc.get(ref)
    assert row["pending_close"] is True
    assert row["reviewer_notes"] == "seal intact, lot verified, recommend close"


@pytest.mark.parametrize(
    "reply",
    [
        "what are the ref pending with review",
        "REF-2026-0159 status",
        "what is the issue",
        "how to fix this complaint issue?",
        "review completed",
        "complete the review",
    ],
)
def test_questions_after_notes_prompt_are_not_saved_as_notes(reply: str):
    from app.modules.agents.graph import _looks_like_notes_reply, _normalize_status_soft

    assert _looks_like_notes_reply(reply, _normalize_status_soft(reply)) is False


def test_question_after_notes_prompt_does_not_close_case():
    from app.modules.agents.graph import router_node

    svc = ReportService()
    ref = _new_report(svc, "Question must not become notes")
    first = status_node(
        {"message": f"complete the review {ref}", "actor": "admin", "role": "admin", "tool_args": {}, "chat_history": []}
    )
    history = [
        {"role": "user", "content": f"complete the review {ref}"},
        {"role": "assistant", "content": first["response"]},
    ]
    q = "what are the ref pending with review"
    assert router_node({"message": q, "actor": "admin", "role": "admin", "chat_history": history})["intent"] != "status"
    row = svc.get(ref)
    assert row["status"] == "New" and not row["reviewer_notes"]


def test_admin_handoff_goes_to_approver_not_self_approved():
    svc = ReportService()
    ref = _new_report(svc, "Admin handoff stays pending")
    try:
        status_node(
            {
                "message": f"{ref} complete the review with seal checked, lot verified",
                "actor": "admin",
                "role": "admin",
                "tool_args": {},
                "chat_history": [],
            }
        )
    except Exception:  # noqa: BLE001  (interrupt() outside graph context)
        pass
    row = svc.get(ref)
    assert row["status"] == "In Review"
    assert row["pending_close"] is True


@pytest.mark.parametrize(
    "message,intent",
    [
        # queue questions → read-only lookup (never a close)
        ("what are the ref pending with review", "lookup"),
        ("which cases are pending approval", "lookup"),
        ("show pending close cases", "lookup"),
        ("how many reports are in review", "lookup"),
        # questions must never write
        ("did the review complete for REF-2026-0159", "lookup"),
        ("why REF-2026-0159 not moved to approver", "lookup"),
        ("how do I submit an intake", "rag"),
        ("what does intake mean", "rag"),
        ("profile a complaint trend", "rag"),
        # intake phrasings
        ("I want to report a complaint for AllergyClear LOT-33018 bottle cracked", "intake"),
        ("raise a new complaint for LOT-88392", "intake"),
        ("create a pqc for NeuroCalm 50mg lot LOT-88392 consumer seal broken", "intake"),
        # review phrasings / typos
        ("take REF-2026-0159 into review", "status"),
        ("complete marked as reviwer", "status"),
        ("mark as complete review for the approver", "status"),
        ("REF-2026-0005 can you please make request close", "status"),
    ],
)
def test_router_rules_without_llm(monkeypatch, message: str, intent: str):
    import app.modules.agents.graph as g

    monkeypatch.setattr(g, "_llm_route", lambda m, h: (None, {"router_source": "llm_disabled"}))
    assert g.router_node({"message": message, "actor": "admin", "role": "admin", "chat_history": []})["intent"] == intent


def test_queue_lookup_filters_by_status():
    from app.modules.agents.graph import lookup_node

    svc = ReportService()
    new_ref = _new_report(svc, "Queue filter new")
    rev_ref = _new_report(svc, "Queue filter in review")
    svc.request_status(rev_ref, "In Review", "reviewer", "reviewer")
    out = lookup_node(
        {"message": "list the new cases", "actor": "admin", "role": "admin", "chat_history": []}
    )
    statuses = {r["status"] for r in out["details"]["reports"]}
    assert statuses == {"New"}
    out = lookup_node(
        {"message": "how many reports are in review", "actor": "admin", "role": "admin", "chat_history": []}
    )
    assert {r["status"] for r in out["details"]["reports"]} == {"In Review"}
    assert out["details"]["count"] >= 1

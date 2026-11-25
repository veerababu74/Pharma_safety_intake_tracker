"""HITL resolve must apply close even when LangGraph interrupt state is missing."""

from __future__ import annotations

from app.db.session import db_manager
from app.modules.agents.graph import LangGraphAgentService
from app.services.chat_service import ChatHistoryService
from app.services.report_service import ReportService

db_manager.init()


def _seed_pending_close(*, lot: str = "LOT-55101") -> tuple[str, dict]:
    reports = ReportService()
    chat = ChatHistoryService()
    created = reports.create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "AllergyClear 5mg",
            "batch_lot_number": lot,
            "date_received": "2026-11-09",
            "reporter_type": "Consumer",
            "description": "HITL resume fallback test",
        },
        actor="reviewer",
        role="reviewer",
    )
    ref = created["reference_id"]
    reports.request_status(ref, "In Review", "reviewer", "reviewer")
    pending = reports.request_status(
        ref,
        "Closed",
        "reviewer",
        "reviewer",
        reviewer_notes="Packaging checked; recommend close",
    )
    assert pending["pending_close"] is True
    # Simulate the broken row from production: HITL stored without session/thread
    hitl = chat.create_hitl(
        session_id="",
        thread_id="",
        username="reviewer",
        tool_name="approve_close",
        payload={
            "reference_id": ref,
            "actor": "reviewer",
            "role": "reviewer",
            "report": pending,
        },
    )
    return ref, hitl


def test_resume_hitl_falls_back_when_thread_missing(monkeypatch):
    ref, hitl = _seed_pending_close(lot="LOT-55102")
    svc = LangGraphAgentService()

    # Graph must not be required for empty-thread HITL rows
    def _boom(*_a, **_k):
        raise AssertionError("graph.invoke should not run without a pending interrupt")

    monkeypatch.setattr(svc.graph, "invoke", _boom)

    out = svc.resume_hitl(
        request_id=hitl["request_id"],
        approved=True,
        resolved_by="approver",
        note="Looks good",
    )
    assert out["details"]["applied_via"] == "report_service"
    assert out["hitl"]["status"] == "approved"

    closed = ReportService().get(ref)
    assert closed["status"] == "Closed"
    assert closed["pending_close"] is False
    assert closed.get("approver_comment") == "Looks good"

    # Retry must be a clean 400-style ValueError, not a misleading KeyError/404
    try:
        svc.resume_hitl(
            request_id=hitl["request_id"],
            approved=True,
            resolved_by="approver",
            note="again",
        )
        raise AssertionError("expected already-resolved ValueError")
    except ValueError as exc:
        assert "already" in str(exc).lower()


def test_resume_hitl_reject_fallback(monkeypatch):
    ref, hitl = _seed_pending_close(lot="LOT-55103")
    svc = LangGraphAgentService()
    monkeypatch.setattr(
        svc.graph,
        "invoke",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no graph")),
    )

    out = svc.resume_hitl(
        request_id=hitl["request_id"],
        approved=False,
        resolved_by="approver",
        note="Need more photos",
    )
    assert out["details"]["applied_via"] == "report_service"
    assert out["hitl"]["status"] == "rejected"

    report = ReportService().get(ref)
    assert report["status"] == "In Review"
    assert report["pending_close"] is False
    assert report.get("approver_comment") == "Need more photos"


def test_reports_api_resolves_matching_agent_hitl():
    from app.api.routes import reports as reports_routes

    ref, hitl = _seed_pending_close(lot="LOT-55104")
    assert hitl["status"] == "pending"

    closed = reports_routes.service.approve_close(ref, "admin", "admin", comment="REST path")
    assert closed["status"] == "Closed"

    # Mimic route side-effect
    reports_routes.chat_svc.resolve_pending_for_reference(
        ref,
        approved=True,
        resolved_by="admin",
        note="Approved via reports API",
    )
    updated = ChatHistoryService().get_hitl(hitl["request_id"])
    assert updated["status"] == "approved"

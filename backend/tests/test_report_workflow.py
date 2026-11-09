"""Intake validation, status transitions, HITL approve/reject, audit rows."""

from __future__ import annotations

import pytest

from app.db.models.audit import AuditLog
from app.db.session import DatabaseKind, db_manager
from app.services.report_service import ReportService


def setup_module():
    db_manager.init()


def _base_payload(**overrides):
    data = {
        "report_type": "Product Quality Complaint",
        "product_name": "NeuroCalm 50mg",
        "batch_lot_number": "LOT-88392",
        "date_received": "2026-03-01",
        "reporter_type": "Consumer",
        "description": "Fictional seal complaint for unit test.",
    }
    data.update(overrides)
    return data


def test_validation_rejects_missing_required_fields():
    svc = ReportService()
    with pytest.raises(ValueError, match="product_name is required"):
        svc.create(_base_payload(product_name=""), actor="operator", role="operator")


def test_validation_rejects_bad_lot_format():
    svc = ReportService()
    with pytest.raises(ValueError, match="LOT-#####"):
        svc.create(_base_payload(batch_lot_number="BADLOT"), actor="operator", role="operator")


def test_ae_requires_event_fields():
    svc = ReportService()
    with pytest.raises(ValueError, match="event_description is required"):
        svc.create(
            _base_payload(
                report_type="Suspected Adverse Event",
                event_description="",
                event_onset_date="",
            ),
            actor="operator",
            role="operator",
        )
    with pytest.raises(ValueError, match="event_onset_date is required"):
        svc.create(
            _base_payload(
                report_type="Suspected Adverse Event",
                event_description="Fictional dizziness",
                event_onset_date="",
            ),
            actor="operator",
            role="operator",
        )


def test_create_writes_audit_and_ref():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="operator", role="operator")
    assert created["reference_id"].startswith("REF-")
    assert created["status"] == "New"

    with db_manager.session(DatabaseKind.AUDIT) as session:
        row = (
            session.query(AuditLog)
            .filter(
                AuditLog.resource_id == created["reference_id"],
                AuditLog.action == "created",
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.actor == "operator"


def test_illegal_new_to_closed_blocked():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="reviewer", role="reviewer")
    with pytest.raises(ValueError, match="Invalid transition"):
        svc.request_status(created["reference_id"], "Closed", "reviewer", "reviewer")


def test_close_requires_reviewer_notes():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="reviewer", role="reviewer")
    ref = created["reference_id"]
    svc.request_status(ref, "In Review", "reviewer", "reviewer")
    with pytest.raises(ValueError, match="reviewer_notes"):
        svc.request_status(ref, "Closed", "reviewer", "reviewer")


def test_hitl_approve_close_flow():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="reviewer", role="reviewer")
    ref = created["reference_id"]
    svc.request_status(ref, "In Review", "reviewer", "reviewer", reviewer_notes="Initial triage")
    pending = svc.request_status(
        ref,
        "Closed",
        "reviewer",
        "reviewer",
        reviewer_notes="Lot verified; packaging photos reviewed; recommend close",
    )
    assert pending["status"] == "In Review"
    assert pending["pending_close"] is True
    assert "Lot verified" in (pending.get("reviewer_notes") or "")

    closed = svc.approve_close(ref, "approver", "approver", comment="Looks complete")
    assert closed["status"] == "Closed"
    assert closed["pending_close"] is False
    assert closed.get("approver_comment") == "Looks complete"

    with db_manager.session(DatabaseKind.AUDIT) as session:
        actions = {
            r.action
            for r in session.query(AuditLog)
            .filter(AuditLog.resource_id == ref)
            .all()
        }
        assert "close_requested" in actions
        assert "hitl_approved" in actions


def test_hitl_reject_close_clears_pending():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="reviewer", role="reviewer")
    ref = created["reference_id"]
    svc.request_status(ref, "In Review", "reviewer", "reviewer")
    svc.request_status(
        ref,
        "Closed",
        "reviewer",
        "reviewer",
        reviewer_notes="Ready for close pending packaging check",
    )

    rejected = svc.reject_close(ref, "approver", "approver", note="Needs more packaging photos")
    assert rejected["status"] == "In Review"
    assert rejected["pending_close"] is False
    assert rejected.get("approver_comment") == "Needs more packaging photos"

    with db_manager.session(DatabaseKind.AUDIT) as session:
        row = (
            session.query(AuditLog)
            .filter(
                AuditLog.resource_id == ref,
                AuditLog.action == "hitl_rejected",
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert "packaging" in (row.details or "")


def test_reject_without_pending_fails():
    svc = ReportService()
    created = svc.create(_base_payload(), actor="reviewer", role="reviewer")
    with pytest.raises(ValueError, match="No pending close"):
        svc.reject_close(created["reference_id"], "approver", "approver")


def test_admin_delete_removes_report_and_audits():
    from app.auth.roles import has_permission

    assert has_permission("admin", "intake:delete")
    assert not has_permission("reviewer", "intake:delete")
    assert not has_permission("operator", "intake:delete")
    assert not has_permission("approver", "intake:delete")

    svc = ReportService()
    created = svc.create(_base_payload(), actor="admin", role="admin")
    ref = created["reference_id"]
    result = svc.delete(ref, actor="admin", role="admin")
    assert result["ok"] is True
    assert result["reference_id"] == ref

    with pytest.raises(KeyError):
        svc.get(ref)

    with db_manager.session(DatabaseKind.AUDIT) as session:
        row = (
            session.query(AuditLog)
            .filter(AuditLog.resource_id == ref, AuditLog.action == "deleted")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.actor == "admin"
        assert "NeuroCalm" in (row.details or "")

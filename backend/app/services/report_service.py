"""Intake report + status workflow + HITL."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.db.models.audit import AuditLog
from app.db.models.core import Report
from app.db.session import DatabaseKind, db_manager

LOT_RE = re.compile(r"^LOT-\d{5}$")
ALLOWED = {
    "New": {"In Review"},
    "In Review": {"Closed"},
    "Closed": set(),
}


def _next_reference_id(session) -> str:
    year = datetime.utcnow().year
    prefix = f"REF-{year}-"
    last = (
        session.query(Report)
        .filter(Report.reference_id.like(f"{prefix}%"))
        .order_by(Report.reference_id.desc())
        .first()
    )
    if not last:
        return f"{prefix}0001"
    seq = int(last.reference_id.split("-")[-1]) + 1
    return f"{prefix}{seq:04d}"


def _audit(actor: str, role: str | None, action: str, resource_id: str, details: str) -> None:
    with db_manager.session(DatabaseKind.AUDIT) as session:
        session.add(
            AuditLog(
                actor=actor,
                role=role,
                action=action,
                resource_type="report",
                resource_id=resource_id,
                details=details,
            )
        )


class ReportService:
    def create(self, payload: dict[str, Any], actor: str, role: str) -> dict[str, Any]:
        report_type = payload["report_type"]
        errors: list[str] = []
        for field in ["product_name", "batch_lot_number", "date_received", "reporter_type", "description"]:
            if not payload.get(field):
                errors.append(f"{field} is required")
        if not LOT_RE.match(payload.get("batch_lot_number", "")):
            errors.append("batch_lot_number must match LOT-#####")
        if report_type == "Suspected Adverse Event":
            if not payload.get("event_description"):
                errors.append("event_description is required for Suspected Adverse Event")
            if not payload.get("event_onset_date"):
                errors.append("event_onset_date is required for Suspected Adverse Event")
        if errors:
            raise ValueError("; ".join(errors))

        with db_manager.session(DatabaseKind.CORE) as session:
            ref = _next_reference_id(session)
            report = Report(
                reference_id=ref,
                report_type=report_type,
                product_name=payload["product_name"],
                batch_lot_number=payload["batch_lot_number"],
                date_received=payload["date_received"],
                reporter_type=payload["reporter_type"],
                description=payload["description"],
                event_description=payload.get("event_description"),
                event_onset_date=payload.get("event_onset_date"),
                status="New",
                created_by=actor,
                updated_by=actor,
            )
            session.add(report)
        _audit(actor, role, "created", ref, "Intake report created")
        return self.get(ref)

    def list(
        self,
        status: str | None = None,
        report_type: str | None = None,
        batch_lot_number: str | None = None,
    ) -> list[dict[str, Any]]:
        with db_manager.session(DatabaseKind.CORE) as session:
            q = session.query(Report)
            if status:
                q = q.filter(Report.status == status)
            if report_type:
                q = q.filter(Report.report_type == report_type)
            if batch_lot_number:
                q = q.filter(Report.batch_lot_number == batch_lot_number.strip().upper())
            rows = q.order_by(Report.created_at.desc()).all()
            return [self._to_dict(r) for r in rows]

    def get(self, reference_id: str) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            r = session.query(Report).filter(Report.reference_id == reference_id).first()
            if not r:
                raise KeyError(reference_id)
            return self._to_dict(r)

    def delete(self, reference_id: str, actor: str, role: str) -> dict[str, Any]:
        """Hard-delete a report from core DB (admin only). Audit row retained."""
        with db_manager.session(DatabaseKind.CORE) as session:
            r = session.query(Report).filter(Report.reference_id == reference_id).first()
            if not r:
                raise KeyError(reference_id)
            snapshot = self._to_dict(r)
            session.delete(r)
        _audit(
            actor,
            role,
            "deleted",
            reference_id,
            f"Deleted report status={snapshot.get('status')}",
        )
        return {"ok": True, "reference_id": reference_id, "deleted": snapshot}

    def request_status(
        self,
        reference_id: str,
        new_status: str,
        actor: str,
        role: str,
        reviewer_notes: str | None = None,
    ) -> dict[str, Any]:
        notes = (reviewer_notes or "").strip()
        with db_manager.session(DatabaseKind.CORE) as session:
            r = session.query(Report).filter(Report.reference_id == reference_id).first()
            if not r:
                raise KeyError(reference_id)
            current = r.status
            # Re-request close while already pending → no-op success
            if current == "In Review" and new_status == "Closed" and r.pending_close:
                return self._to_dict(r)
            # Already at target status → no-op success (e.g. start review twice)
            if new_status == current:
                if notes and current == "In Review":
                    r.reviewer_notes = notes
                    r.updated_by = actor
                return self._to_dict(r)

            if new_status not in ALLOWED.get(current, set()):
                raise ValueError(
                    f"Invalid transition: {current} → {new_status}. "
                    "Allowed workflow is New → In Review → Closed."
                )

            # HITL gate for close — reviewer must add triage notes for the approver
            if current == "In Review" and new_status == "Closed":
                if not notes and not (r.reviewer_notes or "").strip():
                    raise ValueError(
                        "reviewer_notes are required before requesting close. "
                        "Add triage details for the approver (findings, checks done, recommendation)."
                    )
                if notes:
                    r.reviewer_notes = notes
                r.pending_close = True
                r.approver_comment = None
                r.updated_by = actor
                _audit(
                    actor,
                    role,
                    "close_requested",
                    reference_id,
                    "Pending HITL approval",
                )
                return self._to_dict(r)

            r.status = new_status
            r.updated_by = actor
            if notes:
                r.reviewer_notes = notes
            _audit(actor, role, "status_changed", reference_id, f"{current} → {new_status}")
            return self._to_dict(r)

    def approve_close(
        self,
        reference_id: str,
        actor: str,
        role: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        note = (comment or "").strip()
        with db_manager.session(DatabaseKind.CORE) as session:
            r = session.query(Report).filter(Report.reference_id == reference_id).first()
            if not r:
                raise KeyError(reference_id)
            if r.status != "In Review" or not r.pending_close:
                raise ValueError("No pending close approval for this report")
            if not (r.reviewer_notes or "").strip():
                raise ValueError(
                    "Cannot approve: reviewer notes are missing. "
                    "Ask a reviewer to add triage details and re-request close."
                )
            requester = (r.updated_by or "").strip().lower()
            if (
                not get_settings().allow_self_approve
                and requester
                and requester == (actor or "").strip().lower()
            ):
                raise ValueError(
                    "Segregation of duties: the user who requested close cannot also approve it. "
                    "Have a different approver/admin complete HITL, or set ALLOW_SELF_APPROVE=true for training."
                )
            r.status = "Closed"
            r.pending_close = False
            r.approver_comment = note or None
            r.updated_by = actor
        detail = "Close approved" + (" (with comment)" if note else "")
        _audit(actor, role, "hitl_approved", reference_id, detail)
        _audit(actor, role, "status_changed", reference_id, "In Review → Closed")
        return self.get(reference_id)

    def reject_close(
        self, reference_id: str, actor: str, role: str, note: str | None = None
    ) -> dict[str, Any]:
        note_text = (note or "").strip()
        with db_manager.session(DatabaseKind.CORE) as session:
            r = session.query(Report).filter(Report.reference_id == reference_id).first()
            if not r:
                raise KeyError(reference_id)
            if r.status != "In Review" or not r.pending_close:
                raise ValueError("No pending close approval for this report")
            r.pending_close = False
            r.approver_comment = note_text or None
            r.updated_by = actor
        detail = note_text if note_text else "Close rejected; remains In Review"
        _audit(actor, role, "hitl_rejected", reference_id, detail)
        return self.get(reference_id)

    @staticmethod
    def _to_dict(r: Report) -> dict[str, Any]:
        return {
            "reference_id": r.reference_id,
            "report_type": r.report_type,
            "product_name": r.product_name,
            "batch_lot_number": r.batch_lot_number,
            "date_received": r.date_received,
            "reporter_type": r.reporter_type,
            "description": r.description,
            "event_description": r.event_description,
            "event_onset_date": r.event_onset_date,
            "status": r.status,
            "pending_close": r.pending_close,
            "reviewer_notes": r.reviewer_notes,
            "approver_comment": r.approver_comment,
            "created_by": r.created_by,
            "updated_by": r.updated_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

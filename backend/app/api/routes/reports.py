from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_permission
from app.db.models.core import User
from app.schemas.reports import (
    ApproveCloseRequest,
    RejectCloseRequest,
    ReportCreate,
    StatusUpdateRequest,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])
service = ReportService()


@router.post("")
def create_report(
    payload: ReportCreate,
    user: User = Depends(require_permission("intake:create")),
):
    try:
        return service.create(payload.model_dump(), actor=user.username, role=user.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_reports(
    status: str | None = Query(default=None),
    report_type: str | None = Query(default=None),
    user: User = Depends(require_permission("intake:read")),
):
    return service.list(status=status, report_type=report_type)


@router.get("/{reference_id}")
def get_report(reference_id: str, user: User = Depends(require_permission("intake:read"))):
    try:
        return service.get(reference_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc


@router.post("/{reference_id}/status")
def update_status(
    reference_id: str,
    payload: StatusUpdateRequest,
    user: User = Depends(require_permission("workflow:update")),
):
    try:
        return service.request_status(
            reference_id,
            payload.new_status,
            user.username,
            user.role,
            reviewer_notes=payload.reviewer_notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{reference_id}/approve-close")
def approve_close(
    reference_id: str,
    payload: ApproveCloseRequest,
    user: User = Depends(require_permission("workflow:approve_close")),
):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")
    try:
        return service.approve_close(
            reference_id, user.username, user.role, comment=payload.comment
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{reference_id}/reject-close")
def reject_close(
    reference_id: str,
    payload: RejectCloseRequest,
    user: User = Depends(require_permission("workflow:approve_close")),
):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")
    try:
        return service.reject_close(
            reference_id, user.username, user.role, note=payload.note
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

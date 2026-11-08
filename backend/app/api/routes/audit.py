from fastapi import APIRouter, Depends, Query

from app.auth.deps import require_permission
from app.db.models.audit import AuditLog
from app.db.models.core import User
from app.db.session import DatabaseKind, db_manager

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def list_audit_logs(
    limit: int = Query(default=100, le=500),
    user: User = Depends(require_permission("audit:view")),
):
    with db_manager.session(DatabaseKind.AUDIT) as session:
        rows = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "actor": r.actor,
                "role": r.role,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "details": r.details,
            }
            for r in rows
        ]

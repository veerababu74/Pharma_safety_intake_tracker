"""Custom middleware that writes HTTP audit events to the audit SQLite DB."""

from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.models.audit import AuditLog
from app.db.session import DatabaseKind, db_manager

logger = get_logger("audit_middleware")


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        actor = "anonymous"
        role = None
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
            try:
                payload = decode_access_token(token)
                actor = str(payload.get("sub", "anonymous"))
                role = str(payload.get("role")) if payload.get("role") else None
            except Exception:
                pass

        response: Response | None = None
        error_detail = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            error_detail = str(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            status_code = response.status_code if response is not None else 500
            # Skip noisy health checks
            if request.url.path.endswith("/health"):
                pass
            else:
                try:
                    with db_manager.session(DatabaseKind.AUDIT) as session:
                        session.add(
                            AuditLog(
                                actor=actor,
                                role=role,
                                action="http_request",
                                resource_type="http",
                                resource_id=None,
                                method=request.method,
                                path=str(request.url.path),
                                status_code=status_code,
                                details=error_detail or f"latency_ms={latency_ms:.1f}",
                                ip_address=request.client.host if request.client else None,
                            )
                        )
                except Exception as audit_exc:  # noqa: BLE001
                    logger.error("audit_write_failed", error=str(audit_exc))

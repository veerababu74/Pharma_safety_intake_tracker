"""Role constants and permission helpers."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    OPERATOR = "operator"
    APPROVER = "approver"


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "intake:create",
        "intake:read",
        "workflow:update",
        "workflow:approve_close",
        "rag:upload",
        "rag:delete",
        "rag:view",
        "rag:query",
        "agent:chat",
        "obs:view",
        "audit:view",
        "users:manage",
        "eval:run",
    },
    Role.REVIEWER: {
        "intake:create",
        "intake:read",
        "workflow:update",
        "rag:query",
        "rag:view",
        "agent:chat",
        "obs:view",
        "audit:view",
    },
    Role.OPERATOR: {
        "intake:create",
        "intake:read",
        "rag:query",
        "agent:chat",
    },
    Role.APPROVER: {
        "intake:read",
        "workflow:approve_close",
        "rag:query",
        "agent:chat",
        "audit:view",
    },
}


def has_permission(role: str, permission: str) -> bool:
    try:
        return permission in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False

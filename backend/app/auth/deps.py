"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.roles import has_permission
from app.core.security import decode_access_token
from app.db.models.core import User
from app.db.session import DatabaseKind, db_manager

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    username = payload.get("sub")
    with db_manager.session(DatabaseKind.CORE) as session:
        user = session.query(User).filter(User.username == username, User.is_active.is_(True)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        # detach plain values
        session.expunge(user)
        return user


def require_permission(permission: str):
    def _checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _checker


def get_db_session(kind: DatabaseKind):
    def _dep() -> Session:
        raise RuntimeError("Use db_manager.session context in services")

    return _dep

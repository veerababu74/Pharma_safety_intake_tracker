from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models.core import User
from app.db.session import DatabaseKind, db_manager
from app.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    with db_manager.session(DatabaseKind.CORE) as session:
        user = session.query(User).filter(User.username == payload.username).first()
        if (
            not user
            or not user.is_active
            or not verify_password(payload.password, user.hashed_password)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token(user.username, user.role)
        return TokenResponse(
            access_token=token,
            role=user.role,
            username=user.username,
            full_name=user.full_name,
        )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(username=user.username, full_name=user.full_name, role=user.role)

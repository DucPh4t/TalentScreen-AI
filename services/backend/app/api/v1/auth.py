"""Authentication API endpoints: login, logout, and me."""
from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, SESSION_COOKIE_NAME, get_current_context
from app.domain.enums import AccountRole
from app.services.auth import authenticate_user, create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    login_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserProfileDTO(BaseModel):
    id: uuid.UUID
    login_name: str
    display_name: str
    roles: list[str]


class LoginResponse(BaseModel):
    status: str = "ok"
    csrf_token: str
    user: UserProfileDTO


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with login_name and password, sets HttpOnly session cookie."""
    user = await authenticate_user(
        db=db,
        login_name=payload.login_name,
        password=payload.password,
    )
    if not user:
        # Generic error message to prevent account enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thông tin đăng nhập không hợp lệ.",
        )

    session_token, csrf_token, _ = await create_session(db=db, user=user)

    settings = get_settings()
    # In sandbox/local dev, secure=False allows testing over loopback HTTP
    is_secure = settings.APP_ENV == "pilot"

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
        max_age=8 * 3600,  # 8 hours absolute lifetime
    )

    roles = [assoc.role.value for assoc in user.account_roles]

    return LoginResponse(
        csrf_token=csrf_token,
        user=UserProfileDTO(
            id=user.id,
            login_name=user.login_name,
            display_name=user.display_name,
            roles=roles,
        ),
    )


@router.post("/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Revoke current session and clear session cookie."""
    if session_token:
        await revoke_session(db, session_token)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return {"status": "ok", "message": "Đăng xuất thành công."}


@router.get("/me", response_model=UserProfileDTO)
async def get_me(
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Return currently authenticated user profile and roles."""
    roles = [r.value for r in ctx.roles]
    return UserProfileDTO(
        id=ctx.user.id,
        login_name=ctx.user.login_name,
        display_name=ctx.user.display_name,
        roles=roles,
    )

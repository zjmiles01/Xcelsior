"""Authentication endpoints (M10): signup, login, logout, current user.

All four live under `/api/v1/auth`. Signup and login open a server-side
session and set the session as an HTTP-only cookie; the raw token is never
returned in a body, so it can never reach `localStorage` or JavaScript.
Logout revokes the session and clears the cookie. `me` is the frontend's
way to learn whether the browser holds a live session (401 = anonymous).

These routes are public by necessity (you cannot log in while logged out);
they are still rate-limited like the rest of `/api/v1`.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.accounts.deps import require_user
from app.accounts.models import User
from app.accounts.schemas import LoginRequest, SignupRequest, UserOut
from app.accounts.service import (
    EmailAlreadyRegistered,
    authenticate,
    create_session,
    create_user,
    delete_session,
)
from app.core.config import Settings, get_settings
from app.core.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(
    payload: SignupRequest,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Create an account and sign the new user in (a session cookie is set),
    so the client can move straight into resume onboarding."""
    try:
        user = create_user(db, payload.email, payload.password)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from exc
    token = create_session(db, user, settings.session_ttl_days)
    _set_session_cookie(response, token, settings)
    return user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Exchange email + password for a session cookie. A wrong email or
    password is an indistinguishable 401 (no account-enumeration signal)."""
    user = authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_session(db, user, settings.session_ttl_days)
    _set_session_cookie(response, token, settings)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Revoke the current session and clear the cookie. Idempotent: safe to
    call without a valid session (no error, cookie still cleared)."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        delete_session(db, token)
    _clear_session_cookie(response, settings)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> User:
    return user

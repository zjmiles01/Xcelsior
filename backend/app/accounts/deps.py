"""FastAPI auth dependencies (M10).

`get_optional_user` reads the session cookie and resolves it to a user (or
None) — for endpoints that behave differently when signed in but do not
require it. `require_user` is the gate for personal-data routes: no valid
session is a clean 401.

Ownership is *always* derived from the session here, never from a path or
body parameter. A route that needs "the current user's profile" takes
`Depends(require_user)` and scopes its query to `user.id`; it must never
trust a `user_id` sent by the client.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from app.accounts.models import User
from app.accounts.service import resolve_session
from app.core.config import Settings, get_settings
from app.core.db import get_db

_CHALLENGE = {"WWW-Authenticate": "Cookie"}


def get_optional_user(
    request: Request,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return resolve_session(db, token)


def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=401, detail="Authentication required", headers=_CHALLENGE
        )
    return user

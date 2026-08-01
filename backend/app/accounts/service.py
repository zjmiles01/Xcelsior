"""Database services for account and session lifecycle management."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app.accounts.models import Session, User
from app.accounts.security import (
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)


class EmailAlreadyRegistered(Exception):
    """Signup with an email that already has an account."""


class AccountDeletionFailed(Exception):
    """Account deletion did not complete; the transaction was rolled back
    and the account is untouched. Carries no account detail — the caller
    logs and reports it, and neither should name the user."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(db: DbSession, email: str, password: str) -> User:
    """Create an account. Raises EmailAlreadyRegistered if the (normalised)
    email is taken — checked optimistically and again on the unique
    constraint so a race cannot create two accounts for one email."""
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise EmailAlreadyRegistered(normalized)

    user = User(email=normalized, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent signup for the same email
        db.rollback()
        raise EmailAlreadyRegistered(normalized) from exc
    db.refresh(user)
    return user


def authenticate(db: DbSession, email: str, password: str) -> User | None:
    """Return the user iff email + password are valid, else None. Runs the
    password verification even when the email is unknown so the response
    time does not reveal whether an account exists."""
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized))
    if user is None:
        # Waste work against a dummy hash to keep timing uniform.
        verify_password(_DUMMY_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


def create_session(db: DbSession, user: User, ttl_days: int) -> str:
    """Open a new session for the user; returns the raw token for the cookie
    (only its hash is stored)."""
    token = generate_session_token()
    session = Session(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    db.add(session)
    db.commit()
    return token


def resolve_session(db: DbSession, token: str) -> User | None:
    """The user behind a session token, or None if the token is unknown or
    expired. An expired session is deleted opportunistically."""
    session = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if session is None:
        return None
    if _expires_at_utc(session.expires_at) <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None
    return session.user


def delete_session(db: DbSession, token: str) -> None:
    """Revoke a session (logout). Idempotent — an unknown token is a no-op."""
    session = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if session is not None:
        db.delete(session)
        db.commit()


def delete_account(db: DbSession, user: User) -> None:
    """Erase an account and every row that hangs off it, atomically.

    One `DELETE FROM users` is the whole erasure: every ownership edge
    carries `ON DELETE CASCADE` — sessions, resumes, saved_jobs and
    candidate_profiles off `users`, the profile fact tables off
    `candidate_profiles` — so the database, not this function, guarantees
    that nothing of a deleted account survives. That matters twice over: it
    holds on *every* path that removes a user (a migration, a psql session,
    a future admin tool), and it keeps `app.accounts` from having to know
    the shape of `app.profile`, which sits above it in the layering.

    All-or-nothing. Any failure rolls the transaction back and raises
    AccountDeletionFailed, so "half a user" is not a state this can leave
    behind. The caller must treat the session as gone on success — the
    session rows go with the user, and the cookie the browser still holds
    resolves to nothing.
    """
    try:
        db.delete(user)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AccountDeletionFailed("account deletion rolled back") from exc


def _expires_at_utc(value: datetime) -> datetime:
    """Postgres returns aware datetimes; guard against a naive one from any
    driver by assuming UTC, so the comparison never raises."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# A well-formed Argon2 hash of a random string, used only to equalise
# authentication timing for unknown emails. Never matches a real password.
_DUMMY_HASH = hash_password("xcelsior-timing-equaliser")

"""Tests for authenticated account deletion and cascading data cleanup."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.models import Session, User
from app.accounts.service import AccountDeletionFailed, create_session, delete_account
from app.catalog.models import Job
from app.core.config import get_settings
from app.profile.models import (
    CandidateProfile,
    ProfileExperience,
    ProfileSkill,
    Resume,
    SavedJob,
)
from tests.user_world import seed_world

COOKIE = get_settings().session_cookie_name

ACCOUNT = "/api/v1/account"


def _count(db, model, **filters) -> int:
    """Row count straight from the database, unclouded by the identity map."""
    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    return db.scalar(stmt) or 0


def _owned_row_counts(db, user_id: int) -> dict[str, int]:
    """Every table that hangs off a user, counted for that user."""
    profile_ids = db.scalars(
        select(CandidateProfile.id).where(CandidateProfile.user_id == user_id)
    ).all()
    return {
        "users": _count(db, User, id=user_id),
        "sessions": _count(db, Session, user_id=user_id),
        "resumes": _count(db, Resume, user_id=user_id),
        "profiles": _count(db, CandidateProfile, user_id=user_id),
        "saved_jobs": _count(db, SavedJob, user_id=user_id),
        "skills": db.scalar(
            select(func.count())
            .select_from(ProfileSkill)
            .where(ProfileSkill.profile_id.in_(profile_ids))
        )
        if profile_ids
        else 0,
        "experiences": db.scalar(
            select(func.count())
            .select_from(ProfileExperience)
            .where(ProfileExperience.profile_id.in_(profile_ids))
        )
        if profile_ids
        else 0,
    }


@pytest.fixture
def world(db, user):
    return seed_world(db, user)


# ── The auth gate ────────────────────────────────────────────────────────


def test_deleting_an_account_requires_a_session(unauth_client, db, user):
    resp = unauth_client.delete(ACCOUNT)
    assert resp.status_code == 401
    assert _count(db, User, id=user.id) == 1


def test_a_revoked_session_cannot_delete_the_account(db, unauth_client, user):
    """A token that was valid but has been logged out is no better than none."""
    token = create_session(db, user, get_settings().session_ttl_days)
    unauth_client.cookies.set(COOKIE, token)
    unauth_client.post("/api/v1/auth/logout")
    unauth_client.cookies.set(COOKIE, token)

    assert unauth_client.delete(ACCOUNT).status_code == 401
    assert _count(db, User, id=user.id) == 1


# ── Deleting your own account ────────────────────────────────────────────


def test_user_can_delete_their_own_account(client, db, user):
    user_id = user.id
    resp = client.delete(ACCOUNT)
    assert resp.status_code == 204, resp.text
    assert _count(db, User, id=user_id) == 0


def test_deletion_removes_every_record_the_user_owned(client, db, user, world):
    user_id = user.id
    client.post("/api/v1/saved-jobs", json={"job_id": world["backend_job"]})

    before = _owned_row_counts(db, user_id)
    assert all(count > 0 for count in before.values()), before

    assert client.delete(ACCOUNT).status_code == 204

    after = _owned_row_counts(db, user_id)
    assert after == dict.fromkeys(before, 0)


def test_deletion_leaves_the_shared_job_corpus_alone(client, db, world):
    """Only personal data is erased — the jobs the user saved are market
    data owned by nobody, and outlive the account."""
    client.post("/api/v1/saved-jobs", json={"job_id": world["backend_job"]})
    assert client.delete(ACCOUNT).status_code == 204
    assert _count(db, Job, id=world["backend_job"]) == 1


def test_the_email_is_freed_for_a_fresh_signup(client, unauth_client, user):
    """Deletion is real, not a soft flag: the address can be registered
    again, which a `deleted_at` column would have made a 409."""
    email = user.email
    assert client.delete(ACCOUNT).status_code == 204
    resp = unauth_client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "a-brand-new-password"}
    )
    assert resp.status_code == 201, resp.text


# ── You can only delete yourself ─────────────────────────────────────────


def test_deletion_ignores_any_user_id_in_the_request(client, db, user, other_user):
    """The endpoint takes no user id anywhere — path, query, or body. A
    request that smuggles one in still deletes only the caller."""
    caller_id, victim_id = user.id, other_user.id

    resp = client.request(
        "DELETE", f"{ACCOUNT}?user_id={victim_id}", json={"user_id": victim_id}
    )

    assert resp.status_code == 204, resp.text
    assert _count(db, User, id=caller_id) == 0
    assert _count(db, User, id=victim_id) == 1


def test_one_account_deletion_leaves_the_other_account_whole(
    client, other_client, db, user, other_user, world
):
    """`world` (resume, profile, saved job) belongs to `user`; the other
    account deleting itself must not touch a row of it."""
    user_id = user.id
    client.post("/api/v1/saved-jobs", json={"job_id": world["backend_job"]})
    before = _owned_row_counts(db, user_id)

    assert other_client.delete(ACCOUNT).status_code == 204

    assert _count(db, User, id=other_user.id) == 0
    assert _owned_row_counts(db, user_id) == before


# ── The session dies with the account ────────────────────────────────────


def test_the_session_is_invalid_after_deletion(client, db, user):
    """Not just cleared in the browser — the session row is gone, so a
    captured cookie is worthless."""
    token = client.cookies.get(COOKIE)
    assert client.delete(ACCOUNT).status_code == 204

    client.cookies.set(COOKIE, token)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/profiles").status_code == 401
    assert client.delete(ACCOUNT).status_code == 401


def test_deletion_clears_the_session_cookie(client):
    resp = client.delete(ACCOUNT)
    cookie = next(
        header for header in resp.headers.get_list("set-cookie") if header.startswith(COOKIE)
    ).lower()
    # Expired immediately, with the attributes that let the browser match
    # and drop the exact cookie login set.
    assert "max-age=0" in cookie or "expires=" in cookie
    assert "path=/" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_every_session_of_the_account_is_revoked_not_just_the_caller(client, db, user):
    """Signed in on another device? That session goes too."""
    user_id = user.id
    create_session(db, user, get_settings().session_ttl_days)
    assert _count(db, Session, user_id=user_id) == 2

    assert client.delete(ACCOUNT).status_code == 204
    assert _count(db, Session, user_id=user_id) == 0


# ── Failure is atomic ────────────────────────────────────────────────────


def test_a_failed_deletion_rolls_back_and_keeps_the_account_intact(
    db, user, world, monkeypatch
):
    """The delete reaches the database and *then* the commit fails — the
    worst case. Everything must come back, not just the user row."""
    user_id = user.id
    before = _owned_row_counts(db, user_id)

    def failing_commit() -> None:
        db.flush()  # the cascading DELETE really runs…
        raise SQLAlchemyError("simulated database failure")  # …and then this

    monkeypatch.setattr(db, "commit", failing_commit)

    with pytest.raises(AccountDeletionFailed):
        delete_account(db, user)

    monkeypatch.undo()
    assert _owned_row_counts(db, user_id) == before


def test_the_endpoint_reports_a_failure_without_deleting_anything(
    client, db, user, world, monkeypatch
):
    def boom(db_session, account) -> None:
        raise AccountDeletionFailed("account deletion rolled back")

    monkeypatch.setattr("app.accounts.router.delete_account", boom)
    user_id = user.id
    before = _owned_row_counts(db, user_id)

    resp = client.delete(ACCOUNT)

    assert resp.status_code == 500
    # A safe error: no account detail, and an explicit "nothing happened".
    # (HTTPException.detail becomes the problem "title" — core/errors.py.)
    assert user.email not in resp.text
    assert "Nothing was deleted" in resp.json()["title"]

    monkeypatch.undo()
    assert _owned_row_counts(db, user_id) == before
    # The session survives a failed deletion — the user is still signed in.
    assert client.get("/api/v1/auth/me").status_code == 200

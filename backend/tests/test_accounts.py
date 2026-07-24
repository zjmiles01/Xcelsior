"""Account primitives and session service (M10), tested below the HTTP layer.

The password hasher, token hashing, and the signup/authenticate/session
lifecycle are pinned here directly; the endpoint behavior is in test_auth.py.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.accounts.models import Session
from app.accounts.security import (
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.accounts.service import (
    EmailAlreadyRegistered,
    authenticate,
    create_session,
    create_user,
    delete_session,
    normalize_email,
    resolve_session,
)

# ── Password hashing (Argon2) ────────────────────────────────────────────


def test_password_hash_roundtrips():
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "correct horse battery staple") is True
    assert verify_password(h, "wrong password") is False


def test_password_hash_is_salted():
    # Argon2 salts internally: the same password hashes to different strings,
    # and no plaintext is recoverable from the hash.
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert "same-password" not in a


def test_verify_password_tolerates_a_malformed_hash():
    # A corrupt stored hash must read as "wrong password", never raise.
    assert verify_password("not-a-real-argon2-hash", "anything") is False


# ── Session tokens ───────────────────────────────────────────────────────


def test_token_hash_is_deterministic_and_hides_the_token():
    token = generate_session_token()
    assert hash_token(token) == hash_token(token)
    assert token not in hash_token(token)


def test_generated_tokens_are_unique():
    assert generate_session_token() != generate_session_token()


# ── Users ────────────────────────────────────────────────────────────────


def test_normalize_email_lowercases_and_trims():
    assert normalize_email("  Foo@Bar.COM ") == "foo@bar.com"


def test_create_user_persists_a_hashed_password(db):
    user = create_user(db, "person@example.com", "a-good-password")
    assert user.id is not None
    assert user.email == "person@example.com"
    assert user.password_hash != "a-good-password"
    assert verify_password(user.password_hash, "a-good-password")


def test_create_user_rejects_duplicate_email(db):
    create_user(db, "dupe@example.com", "a-good-password")
    with pytest.raises(EmailAlreadyRegistered):
        create_user(db, "DUPE@example.com", "another-password")


def test_authenticate(db):
    create_user(db, "auth@example.com", "the-right-password")
    assert authenticate(db, "auth@example.com", "the-right-password") is not None
    assert authenticate(db, "AUTH@example.com", "the-right-password") is not None  # case
    assert authenticate(db, "auth@example.com", "the-wrong-password") is None
    assert authenticate(db, "ghost@example.com", "anything-at-all") is None


# ── Sessions ─────────────────────────────────────────────────────────────


def test_create_and_resolve_session(db):
    user = create_user(db, "sess@example.com", "a-good-password")
    token = create_session(db, user, ttl_days=14)
    resolved = resolve_session(db, token)
    assert resolved is not None and resolved.id == user.id


def test_resolve_unknown_token_is_none(db):
    assert resolve_session(db, "not-a-real-token") is None


def test_expired_session_is_rejected_and_purged(db):
    user = create_user(db, "expired@example.com", "a-good-password")
    token = create_session(db, user, ttl_days=-1)  # already expired
    assert resolve_session(db, token) is None
    # The expired row is cleaned up opportunistically.
    remaining = db.query(Session).filter(Session.user_id == user.id).count()
    assert remaining == 0


def test_delete_session_revokes(db):
    user = create_user(db, "revoke@example.com", "a-good-password")
    token = create_session(db, user, ttl_days=14)
    delete_session(db, token)
    assert resolve_session(db, token) is None


def test_session_stores_only_the_hash_not_the_token(db):
    user = create_user(db, "hashonly@example.com", "a-good-password")
    token = create_session(db, user, ttl_days=14)
    row = db.query(Session).filter(Session.user_id == user.id).one()
    assert row.token_hash == hash_token(token)
    assert row.token_hash != token
    now = datetime.now(UTC)
    assert row.expires_at > now
    assert row.expires_at <= now + timedelta(days=14, seconds=5)

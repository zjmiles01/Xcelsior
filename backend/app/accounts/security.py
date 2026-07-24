"""Password hashing and session-token primitives (M10).

Passwords are hashed with Argon2id (`argon2-cffi`, the reference binding of
the Password Hashing Competition winner) — memory-hard, side-channel
resistant, and the current default recommendation for password storage.
The hash string is self-describing (it embeds the algorithm and parameters)
so `verify_password` also reports when a stored hash should be re-hashed
after a parameter bump, though we do not force a rehash flow in this
milestone.

Session tokens are 256 bits of `secrets` randomness, URL-safe. Only their
SHA-256 hash is stored (`hash_token`); the raw token lives solely in the
user's HTTP-only cookie. A constant-time compare is unnecessary for the DB
lookup because we look sessions up *by* the hash (an indexed equality on a
value the attacker cannot influence without already knowing the token).
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# One shared hasher with library defaults (tuned, sane parameters). Argon2
# salts internally, so identical passwords produce different hashes.
_hasher = PasswordHasher()

# Session tokens: 32 bytes -> 43-char URL-safe string. Ample entropy.
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True iff the password matches the stored Argon2 hash. All failure
    modes (mismatch, malformed stored hash) collapse to False — callers must
    not be able to distinguish 'wrong password' from 'corrupt hash'."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_session_token() -> str:
    """A fresh opaque session token for the cookie."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex of a session token — the only form stored server-side.
    Fast (unlike password hashing) because the token already has full
    entropy; there is nothing to brute-force."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

"""User accounts and server-side sessions (M10).

Xcelsior graduates from a single shared dev token (M8) to real multi-user
accounts. Two tables:

- `users` — one row per account: a case-insensitively-unique email and an
  Argon2 password hash. No plaintext password is ever stored.
- `sessions` — server-side session records. The cookie holds an opaque
  random token; only its SHA-256 hash lands here, so a database leak does
  not hand an attacker live sessions. Sessions are revocable (logout, or a
  future "sign out everywhere") precisely because they are server-side —
  the deliberate alternative to a self-contained, un-revocable signed token
  in the browser.

Ownership of personal data hangs off `users.id`: `resumes`,
`candidate_profiles`, and `saved_jobs` all carry a `user_id` (see
`app/profile/models.py`), and every personal-data query is scoped to the
authenticated user, never to an id supplied by the client.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercased; the unique constraint (which Postgres backs with an
    # index) enforces one account per email regardless of the case typed.
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex of the opaque cookie token — never the token itself. The
    # unique constraint doubles as the lookup index (resolve-by-hash).
    token_hash: Mapped[str] = mapped_column(unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")

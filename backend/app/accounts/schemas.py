"""Auth request/response schemas (M10).

Email is validated with a deliberately conservative regex rather than
pulling in `email-validator`: this is an MVP account system, not a mail
deliverability gate, and the format check only needs to reject obvious
garbage before the unique-index and login flows take over. Passwords have a
minimum length; there is no maximum-complexity theatre (length is the
signal that matters), but Argon2 hashing bounds practical input size.
"""

import re

from pydantic import BaseModel, ConfigDict, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class Credentials(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        cleaned = value.strip()
        if not _EMAIL_RE.match(cleaned):
            raise ValueError("a valid email address is required")
        return cleaned


class SignupRequest(Credentials):
    @field_validator("password")
    @classmethod
    def _password_length(cls, value: str) -> str:
        if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
            raise ValueError(
                f"password must be between {MIN_PASSWORD_LENGTH} and "
                f"{MAX_PASSWORD_LENGTH} characters"
            )
        return value


class LoginRequest(Credentials):
    """Login does not re-validate password length: complexity rules change
    over time and must never lock an existing account out of signing in."""


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str

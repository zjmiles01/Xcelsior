"""Contact facts from the resume's header block (text above the first
section header): email, US-format phone, and — conservatively — a name.

The name rule is deliberately strict (2-4 capitalized tokens, no digits,
no email, first non-empty line only): a wrong name on a profile is worse
than a blank one the user fills in during review. Same conservatism-over-
coverage stance as the geocoder.
"""

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}"
)
_NAME_TOKEN_RE = re.compile(r"[A-Z][A-Za-z'’.-]*")


def extract_email(header_text: str) -> str | None:
    m = _EMAIL_RE.search(header_text)
    return m.group(0) if m else None


def extract_phone(header_text: str) -> str | None:
    m = _PHONE_RE.search(header_text)
    return m.group(0).strip() if m else None


def extract_name(header_text: str) -> str | None:
    for line in header_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if "@" in stripped or any(ch.isdigit() for ch in stripped) or "|" in stripped:
            return None
        tokens = stripped.split()
        if not 2 <= len(tokens) <= 4 or len(stripped) > 60:
            return None
        if all(_NAME_TOKEN_RE.fullmatch(tok) for tok in tokens):
            return stripped
        return None
    return None

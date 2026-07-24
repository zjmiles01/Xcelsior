"""Years-of-experience and work-arrangement inference from description text.

Experience level resolution order: title tokens (strongest signal, handled
in title.py) → years-of-experience patterns here. Arrangement: explicit
phrases beat the location-text heuristic from ingestion.
"""

import re

_YOE_RE = re.compile(
    r"(?:at least\s+|minimum(?: of)?\s+)?(\d{1,2})\s*\+?\s*(?:[-–]\s*(\d{1,2})\s*)?"
    r"years?(?:'|s)?\s+(?:of\s+)?(?:[\w/-]+\s+){0,3}?experience",
    re.IGNORECASE,
)

_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_REMOTE_RE = re.compile(
    r"fully remote|remote[- ]first|100% remote|work from anywhere|remote position|remote role"
    r"|remote \(?(?:us|united states)\)?",
    re.IGNORECASE,
)
_ONSITE_RE = re.compile(r"on[- ]?site|in[- ]office|in the office", re.IGNORECASE)


def extract_years_of_experience(text: str) -> int | None:
    """Minimum required years, from the first plausible YOE phrase."""
    for match in _YOE_RE.finditer(text):
        years = int(match.group(1))
        if 0 < years <= 20:
            return years
    return None


def level_from_years(years: int) -> str:
    if years < 2:
        return "entry"
    if years < 5:
        return "mid"
    if years < 8:
        return "senior"
    return "staff_plus"


def infer_arrangement(text: str, location_is_remote: bool) -> str | None:
    """Hybrid wins over remote (postings often say 'hybrid' while also using
    the word remote); explicit onsite phrasing beats the location flag."""
    if _HYBRID_RE.search(text):
        return "hybrid"
    if _REMOTE_RE.search(text) or location_is_remote:
        return "remote"
    if _ONSITE_RE.search(text):
        return "onsite"
    return None

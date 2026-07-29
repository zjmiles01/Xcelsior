"""The employment-type vocabulary: the values `jobs.employment_type` may hold.

Lives in the catalog layer because both pipelines above it need it and they
are independent siblings (import contract §"Layered architecture"):
ingestion maps what a source declares onto these values, extraction infers
them from text, and the filter contract validates queries against them.

Only the vocabulary and the source-string mapping live here — inferring a
type from description text is extraction's job (app/extraction/employment.py).
"""

import re
from typing import Literal

EmploymentType = Literal[
    "full_time", "part_time", "internship", "contract", "temporary", "unknown"
]

FULL_TIME = "full_time"
PART_TIME = "part_time"
INTERNSHIP = "internship"
CONTRACT = "contract"
TEMPORARY = "temporary"
UNKNOWN = "unknown"

EMPLOYMENT_TYPES: tuple[str, ...] = (
    FULL_TIME, PART_TIME, INTERNSHIP, CONTRACT, TEMPORARY, UNKNOWN,
)

# Declared-value vocabulary. Sources spell these many ways ("Full-time",
# "FullTime", "full time"), so lookup happens on a punctuation-stripped,
# lowercased key rather than the raw string.
_DECLARED: dict[str, str] = {
    "fulltime": FULL_TIME,
    "full": FULL_TIME,
    "fte": FULL_TIME,
    "permanent": FULL_TIME,
    "regular": FULL_TIME,
    "parttime": PART_TIME,
    "part": PART_TIME,
    "intern": INTERNSHIP,
    "interns": INTERNSHIP,
    "internship": INTERNSHIP,
    "internships": INTERNSHIP,
    "coop": INTERNSHIP,
    "coopinternship": INTERNSHIP,
    "internshipcoop": INTERNSHIP,
    "student": INTERNSHIP,
    "apprentice": INTERNSHIP,
    "apprenticeship": INTERNSHIP,
    "contract": CONTRACT,
    "contractor": CONTRACT,
    "contracttohire": CONTRACT,
    "consultant": CONTRACT,
    "consulting": CONTRACT,
    "freelance": CONTRACT,
    "temporary": TEMPORARY,
    "temp": TEMPORARY,
    "seasonal": TEMPORARY,
    "fixedterm": TEMPORARY,
}

_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def normalize_declared(value: str | None) -> str | None:
    """Map a source-declared employment string onto our vocabulary.

    Returns None for anything unrecognized so the caller falls through to
    text classification rather than inheriting a guess — Greenhouse
    metadata in particular is free text, and an unmapped value there means
    "the board said something we don't understand", not "the board is
    telling us this is full-time".
    """
    if not value:
        return None
    key = _PUNCT_RE.sub("", value.lower())
    if not key:
        return None
    if key in _DECLARED:
        return _DECLARED[key]
    # Compound phrasings ("Full-time Employee", "Intern / Co-op", "Regular
    # Full Time"): fall back to the first token that carries a meaning.
    for token in _PUNCT_RE.sub(" ", value.lower()).split():
        if token in _DECLARED:
            return _DECLARED[token]
    return None

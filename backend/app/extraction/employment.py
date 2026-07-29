"""Employment-type inference from posting text: internships, contracts, and friends.

Two signals, in strict precedence order:

  1. What the source declared. Lever states it outright
     (`categories.commitment`); some Greenhouse boards carry it in their
     free-form metadata. A declared value is a fact about the posting and
     always wins.
  2. What the text says. Title first (titles are terse and deliberate —
     "Software Engineering Intern" is unambiguous), description second.

Pure module, same contract as title.py / experience.py: no I/O, so the
live pipeline, the gold-set evaluation, and unit tests all run it
identically. The vocabulary itself lives one layer down, in
app/catalog/employment.py, because ingestion needs it too.

Absent any signal the answer is full_time, not unknown: on company ATS
boards a role with an ordinary engineering title and no qualifier is
overwhelmingly a permanent one, and calling that "unknown" would push most
of the corpus into a bucket nobody filters by. unknown is reserved for
postings with nothing to classify at all.
"""

import re

from app.catalog.employment import (
    CONTRACT,
    FULL_TIME,
    INTERNSHIP,
    PART_TIME,
    TEMPORARY,
    UNKNOWN,
    normalize_declared,
)

# Only the first ~4k characters of a description are scanned for type
# markers: employment terms are stated up front, while the tail is
# boilerplate ("we also hire interns", EEO text) that produces false
# positives.
_TEXT_SCAN_LIMIT = 4000

# Word-boundary anchored so "internal", "international", and "students of
# the craft" can't masquerade as internships. "co-op" allows the hyphen or
# a space; bare "coop" is deliberately excluded (co-operatives, chicken coops).
# New-grad and university-graduate roles are deliberately absent: they are
# permanent positions, and their entry-level-ness is already captured by
# title.py's level tokens. Calling them internships would put full-time
# jobs behind the internship filter.
_INTERNSHIP_TITLE_RE = re.compile(
    r"\b(?:intern|interns|internship|internships|co[- ]op|co[- ]ops"
    r"|apprentice(?:ship)?)\b",
    re.IGNORECASE,
)
# "student" only counts as an internship marker next to hiring vocabulary —
# on its own it is as likely to describe the customers as the hire. Words
# for what a student *is here to do* qualify; words for a thing that is run
# for students do not, or "Director of Student Programs" becomes an intern.
_STUDENT_TITLE_RE = re.compile(
    r"\b(?:student\s+(?:intern|internship|worker|researcher|associate|trainee)"
    r"|(?:summer|winter|fall|spring)\s+student"
    r"|(?:graduate|undergraduate|phd|master'?s?)\s+(?:intern|student))",
    re.IGNORECASE,
)
_INTERNSHIP_TEXT_RE = re.compile(
    r"(?:\binternship\s+(?:program|opportunit|position|role)"
    r"|\b(?:this|our|the|summer|winter|fall|spring)\s+internship"
    r"|\bco[- ]op\s+(?:program|student|term|position)"
    r"|\bcurrently\s+enrolled\s+in"
    r"|\bpursuing\s+a\s+(?:bachelor|master|ba\b|bs\b|ms\b|degree)"
    r"|\brising\s+(?:junior|senior|sophomore))",
    re.IGNORECASE,
)

_PART_TIME_RE = re.compile(r"\bpart[- ]time\b", re.IGNORECASE)
_CONTRACT_TITLE_RE = re.compile(r"\b(?:contract|contractor|consultant|freelance)\b", re.IGNORECASE)
_CONTRACT_TEXT_RE = re.compile(
    r"(?:\bcontract\s+(?:position|role|opportunity|basis|assignment)"
    r"|\b(?:\d{1,2}|six|three|twelve)[- ]month\s+contract"
    r"|\bw2\s+contract|\bcorp[- ]to[- ]corp|\b1099\s+(?:contractor|basis))",
    re.IGNORECASE,
)
_TEMPORARY_RE = re.compile(
    r"\b(?:temporary|seasonal|fixed[- ]term|temp\s+(?:position|role|assignment))\b",
    re.IGNORECASE,
)


def classify_employment_type(title: str, text: str = "", declared: str | None = None) -> str:
    """Best available employment type for one posting.

    `declared` is the source's own statement, raw; it wins whenever we
    recognize it. Otherwise the title decides, then the description body.
    """
    from_declared = normalize_declared(declared)
    if from_declared is not None:
        return from_declared

    title = title or ""
    body = (text or "")[:_TEXT_SCAN_LIMIT]
    if not title.strip() and not body.strip():
        return UNKNOWN

    # Title order matters: internship outranks everything else (a "Contract
    # Design Intern" is an intern), then part-time, then contract/temp.
    if _INTERNSHIP_TITLE_RE.search(title) or _STUDENT_TITLE_RE.search(title):
        return INTERNSHIP
    if _PART_TIME_RE.search(title):
        return PART_TIME
    if _CONTRACT_TITLE_RE.search(title):
        return CONTRACT
    if _TEMPORARY_RE.search(title):
        return TEMPORARY

    if body:
        if _INTERNSHIP_TEXT_RE.search(body):
            return INTERNSHIP
        if _PART_TIME_RE.search(body):
            return PART_TIME
        if _CONTRACT_TEXT_RE.search(body):
            return CONTRACT
        if _TEMPORARY_RE.search(body):
            return TEMPORARY

    return FULL_TIME

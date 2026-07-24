"""Education entry parsing inside a resume's education section.

An entry is an institution line (contains a school word: University,
College, ...) with the degree/year lines that follow it, or a degree
line on its own when no institution line precedes it. A second degree
line under the same institution opens a new entry that inherits the
institution (double majors/degrees list one school once).

Degree normalization keeps both forms (degree_raw as printed,
degree_level normalized) — the same raw-plus-normalized pattern salary
uses on jobs. Abbreviations are matched case-sensitively so "MA" the
state and "as"/"ba" the words can't become degrees; worded forms
("Master of ...") match case-insensitively.
"""

import re
from dataclasses import dataclass

from app.profile.dates import find_date_range

_INSTITUTION_RE = re.compile(
    r"\b(university|college|institute|school|polytechnic|academy|conservatory)\b",
    re.IGNORECASE,
)

# (level, case-insensitive worded form, case-sensitive abbreviation form).
# Dotted abbreviations tolerate a trailing-dot-less form (B.S / B.S.).
_DEGREE_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "doctorate",
        re.compile(r"\bph\.?\s?d\b|\bdoctor(?:ate)? of\b|\bd\.phil\b", re.IGNORECASE),
    ),
    (
        "master",
        re.compile(
            r"(?i:\bmaster(?:'s|s)?(?: of| in)?\b)"
            r"|\bM\.\s?S(?:c)?\.?\b|\bM\.\s?A\.?\b|\bM\.?Eng\.?\b|\bMBA\b|\bMS(?:c)?\b|\bM\.?Tech\b"
        ),
    ),
    (
        "bachelor",
        re.compile(
            r"(?i:\bbachelor(?:'s|s)?(?: of| in)?\b)"
            r"|\bB\.\s?S(?:c|E)?\.?\b|\bB\.\s?A\.?\b|\bB\.?Eng\.?\b|\bBS(?:c|E)?\b|\bBA\b"
            r"|\bB\.?Tech\b"
        ),
    ),
    (
        "associate",
        re.compile(r"(?i:\bassociate(?:'s|s)? (?:degree|of)\b)|\bA\.\s?[AS]\.?\b"),
    ),
]

_FIELD_RE = re.compile(
    r"\b(?:in|of)\s+([A-Z][A-Za-z&/+-]*(?:\s+[A-Z&][A-Za-z&/+-]*)*)"
)


@dataclass(frozen=True)
class EducationEntry:
    institution: str | None
    degree_raw: str | None
    degree_level: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None
    start: int  # absolute span in the resume text
    end: int


def parse_education(text: str, section_start: int, section_end: int) -> list[EducationEntry]:
    lines: list[tuple[str, int, int]] = []
    pos = section_start
    for line in text[section_start:section_end].split("\n"):
        lines.append((line, pos, pos + len(line)))
        pos += len(line) + 1

    # Group lines into entries: institution line starts one; a degree line
    # starts one too when there's no open entry or the open entry already
    # has a degree.
    groups: list[dict] = []
    current: dict | None = None
    for line, start, end in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_institution = bool(_INSTITUTION_RE.search(stripped))
        degree = match_degree_level(stripped)

        if is_institution and not degree:
            current = {
                "institution": stripped.rstrip(",;"),
                "lines": [(line, start, end)],
                "degree_line": None,
            }
            groups.append(current)
            continue
        if degree and (current is None or current["degree_line"] is not None):
            inherited = current["institution"] if current else None
            current = {
                "institution": inherited,
                "lines": [(line, start, end)],
                "degree_line": stripped,
            }
            groups.append(current)
            continue
        if current is not None:
            current["lines"].append((line, start, end))
            if degree and current["degree_line"] is None:
                current["degree_line"] = stripped

    entries: list[EducationEntry] = []
    for group in groups:
        block = "\n".join(line for line, _, _ in group["lines"])
        degree_raw, degree_level = None, None
        if group["degree_line"]:
            degree_raw, degree_level = _degree_forms(group["degree_line"])
        start_year, end_year = _years(block)
        entries.append(
            EducationEntry(
                institution=group["institution"],
                degree_raw=degree_raw,
                degree_level=degree_level,
                field_of_study=_field(group["degree_line"] or block),
                start_year=start_year,
                end_year=end_year,
                start=group["lines"][0][1],
                end=group["lines"][-1][2],
            )
        )
    return entries


def match_degree_level(line: str) -> str | None:
    for level, pattern in _DEGREE_PATTERNS:
        if pattern.search(line):
            return level
    return None


def _degree_forms(line: str) -> tuple[str, str | None]:
    """(degree_raw, degree_level): raw is the degree phrase up to the first
    comma (the part of the line that names the degree)."""
    return line.split(",")[0].strip(), match_degree_level(line)


def _field(text: str) -> str | None:
    for level_match in (p.search(text) for _, p in _DEGREE_PATTERNS):
        if not level_match:
            continue
        m = _FIELD_RE.search(text, level_match.end())
        if m:
            return m.group(1).strip()
    return None


def _years(block: str) -> tuple[int | None, int | None]:
    found = find_date_range(block)
    if found:
        return found.start.year, found.end.year if found.end else None
    # A single year is a graduation year.
    single = re.search(r"\b(19|20)\d{2}\b", block)
    if single:
        return None, int(single.group(0))
    return None, None

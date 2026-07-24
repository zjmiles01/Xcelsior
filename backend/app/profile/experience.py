"""Work-history entry parsing inside a resume's experience section.

Anchor rule: an entry is announced by a *date line* — a non-bullet line
containing a parseable date range with little other text. The entry's
heading (title/company) is either the leftover text on that same line
("Acme | Senior Engineer | 2020 - Present") or up to two non-bullet
lines directly above it; bullet lines in between entries become the
entry's summary.

Heading resolution is deterministic and conservative: a part is the
title if it contains a role word (engineer, developer, manager, ...);
when neither or both parts look like a title, the whole heading becomes
`title_raw` and company stays None — a visible gap the review UI asks
the user to fix, never a guess.

All offsets returned are absolute (into the full resume text), so
evidence spans stay valid regardless of which section they came from.
"""

import re
from dataclasses import dataclass

from app.profile.dates import DateRange, find_date_range

_BULLET_RE = re.compile(r"^\s*[-•*·▪‣◦]")
# Text allowed on a date line besides the date itself before we stop
# treating it as an entry anchor (a prose sentence that merely mentions
# a date range is content, not structure).
_MAX_NON_DATE_CHARS = 70
_MAX_HEADING_LINES = 2

_ROLE_WORDS = re.compile(
    r"\b(engineer(?:ing)?|developer|architect|scientist|analyst|manager|"
    r"director|lead|consultant|administrator|admin|designer|intern(?:ship)?|"
    r"sre|devops|programmer|specialist|researcher|head|vp|founder|cto|ceo|"
    r"principal|staff)\b",
    re.IGNORECASE,
)

_SPLIT_SEPARATORS = [" at ", " @ ", " | ", " – ", " — ", " - ", ", "]


@dataclass(frozen=True)
class ExperienceEntry:
    title_raw: str
    company: str | None
    dates: DateRange | None
    summary: str  # bullet/body text of the entry, may be ""
    start: int  # absolute span of the whole entry in the resume text
    end: int


def parse_experience(text: str, section_start: int, section_end: int) -> list[ExperienceEntry]:
    """Parse entries out of text[section_start:section_end]."""
    lines = _lines_with_offsets(text, section_start, section_end)

    # Pass 1: find anchor (date) lines.
    anchors: list[tuple[int, DateRange]] = []  # (line index, range)
    for i, (line, _, _) in enumerate(lines):
        if _BULLET_RE.match(line):
            continue
        found = find_date_range(line)
        if found is None:
            continue
        non_date = line[: found.match_start] + line[found.match_end :]
        if len(non_date.strip()) <= _MAX_NON_DATE_CHARS:
            anchors.append((i, found))

    # Pass 2: for each anchor, claim heading lines above it.
    # Tuples are (first_line, anchor_idx, date_range, heading_parts).
    entries: list[tuple[int, int, DateRange, list[str]]] = []
    prev_claimed = -1  # last line index owned by the previous entry's heading+anchor
    for anchor_idx, date_range in anchors:
        line, _, _ = lines[anchor_idx]
        leftover = (line[: date_range.match_start] + line[date_range.match_end :]).strip(" \t|,–—-")
        heading_parts: list[str] = [leftover] if len(leftover) >= 4 else []
        first_line = anchor_idx
        if not heading_parts:
            j = anchor_idx - 1
            while (
                j > prev_claimed
                and anchor_idx - j <= _MAX_HEADING_LINES
                and lines[j][0].strip()
                and not _BULLET_RE.match(lines[j][0])
                and find_date_range(lines[j][0]) is None
            ):
                heading_parts.insert(0, lines[j][0].strip())
                first_line = j
                j -= 1
        prev_claimed = anchor_idx
        entries.append((first_line, anchor_idx, date_range, heading_parts))

    results: list[ExperienceEntry] = []
    for k, (first_line, anchor_idx, date_range, heading_parts) in enumerate(entries):
        body_start = anchor_idx + 1
        body_end = entries[k + 1][0] if k + 1 < len(entries) else len(lines)
        summary = "\n".join(
            lines[j][0].strip() for j in range(body_start, body_end) if lines[j][0].strip()
        )
        title, company = _resolve_heading(heading_parts)
        if title is None:
            continue  # a date range with no heading at all is not an entry
        entry_start = lines[first_line][1]
        entry_end = lines[body_end - 1][2] if body_end > first_line else lines[anchor_idx][2]
        results.append(
            ExperienceEntry(
                title_raw=title,
                company=company,
                dates=date_range,
                summary=summary,
                start=entry_start,
                end=entry_end,
            )
        )
    return results


def _lines_with_offsets(
    text: str, section_start: int, section_end: int
) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    pos = section_start
    for line in text[section_start:section_end].split("\n"):
        out.append((line, pos, pos + len(line)))
        pos += len(line) + 1
    return out


def _resolve_heading(parts: list[str]) -> tuple[str | None, str | None]:
    """(title_raw, company) from 1-2 heading fragments."""
    fragments = [p.strip(" \t|,–—-") for p in parts if p.strip(" \t|,–—-")]
    if not fragments:
        return None, None

    if len(fragments) == 1:
        return _split_single_heading(fragments[0])

    a, b = fragments[0], fragments[1]
    a_title, b_title = bool(_ROLE_WORDS.search(a)), bool(_ROLE_WORDS.search(b))
    if a_title and not b_title:
        return a, b
    if b_title and not a_title:
        return b, a
    return " — ".join(fragments), None  # ambiguous: visible, user-fixable


def _split_single_heading(heading: str) -> tuple[str, str | None]:
    for sep in _SPLIT_SEPARATORS:
        if sep not in heading:
            continue
        left, right = heading.split(sep, 1)
        left, right = left.strip(), right.strip()
        if not left or not right:
            continue
        left_title = bool(_ROLE_WORDS.search(left))
        right_title = bool(_ROLE_WORDS.search(right))
        if left_title and not right_title:
            return left, right
        if right_title and not left_title:
            return right, left
    return heading, None

"""Detect the semi-structure of job descriptions: requirements,
nice-to-haves, responsibilities, benefits.

Section spans are character offsets into the extracted plain text and are
persisted (job_sections), so the Job Detail page renders exactly what the
extractor saw and requirement levels stay explainable.
"""

import re
from dataclasses import dataclass

SECTION_KINDS = ("required", "preferred", "responsibilities", "benefits", "other")

_HEADER_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "preferred",
        re.compile(
            r"^(nice to have|nice-to-have|preferred qualification|preferred skill"
            r"|bonus point|bonus|a plus|pluses|it'?d be great|great to have"
            r"|extra credit|preferred experience"
            r"|even better|not required)",
            re.IGNORECASE,
        ),
    ),
    (
        "required",
        re.compile(
            r"^(requirements?|qualifications?|what you('| wi)ll need"
            r"|what we('| a)re looking for"
            r"|must[- ]haves?|minimum qualification|basic qualification|about you|who you are"
            r"|what you bring|your background|skills? (and|&) experience|what you need"
            r"|you (should )?have|we('| a)re looking for"
            r"|required (skills?|experience|qualification))",
            re.IGNORECASE,
        ),
    ),
    (
        "responsibilities",
        re.compile(
            r"^(responsibilit|what you('| wi)ll (do|be doing|work on|own)|the role"
            r"|your (role|impact)"
            r"|day[- ]to[- ]day|in this role|you will|about the (role|job|position)|duties"
            r"|what you('| wi)ll (accomplish|achieve))",
            re.IGNORECASE,
        ),
    ),
    (
        "benefits",
        re.compile(
            r"^(benefits?|perks?|what we offer|compensation|pay (range|transparency)|salary"
            r"|we offer|total rewards|why (join|work))",
            re.IGNORECASE,
        ),
    ),
]

_MAX_HEADER_LENGTH = 90


@dataclass(frozen=True)
class Section:
    kind: str
    start: int  # offset of first content char after the header line
    end: int


def detect_sections(text: str) -> list[Section]:
    """Scan line by line; a short line matching a header pattern opens a
    section that runs until the next header (or end of document)."""
    headers: list[tuple[str, int, int]] = []  # (kind, header_start, header_end)
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip().strip(":•-– ").strip()
        if 0 < len(stripped) <= _MAX_HEADER_LENGTH:
            for kind, pattern in _HEADER_PATTERNS:
                if pattern.match(stripped):
                    headers.append((kind, offset, offset + len(line)))
                    break
        offset += len(line) + 1

    sections: list[Section] = []
    for i, (kind, _, header_end) in enumerate(headers):
        content_start = header_end + 1
        content_end = headers[i + 1][1] if i + 1 < len(headers) else len(text)
        if content_start < content_end:
            sections.append(Section(kind=kind, start=content_start, end=content_end))
    return sections


def requirement_level_at(sections: list[Section], pos: int) -> str:
    """Map a character position to required/preferred/mentioned."""
    for section in sections:
        if section.start <= pos < section.end:
            if section.kind in ("required", "preferred"):
                return section.kind
            break
    return "mentioned"

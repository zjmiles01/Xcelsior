"""Resume section detection: summary, skills, experience, education,
projects, certifications.

Same span mechanics as job-description sections (app/extraction/sections):
character offsets into the parsed resume text, so every downstream fact
stays traceable to the exact text it came from. Headers are matched as
whole standalone lines (fullmatch, not prefix): "Experience" is a header,
"Experience with Python" is content.
"""

import re
from dataclasses import dataclass

RESUME_SECTION_KINDS = (
    "summary",
    "skills",
    "experience",
    "education",
    "projects",
    "certifications",
)

_HEADER_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "summary",
        re.compile(
            r"(professional |career |executive )?summary|(career )?objective"
            r"|profile|about( me)?",
            re.IGNORECASE,
        ),
    ),
    (
        "skills",
        re.compile(
            r"((technical|core|key) )?skills( (&|and) (tools|technologies|abilities))?"
            r"|technologies|technical proficiencies|core competencies|tech stack"
            r"|tools( (&|and) technologies)?",
            re.IGNORECASE,
        ),
    ),
    (
        "experience",
        re.compile(
            r"((work|professional|relevant|career) )?experience"
            r"|employment( history)?|work history|career history",
            re.IGNORECASE,
        ),
    ),
    (
        "education",
        re.compile(
            r"education( (&|and) training)?|academic background|academics",
            re.IGNORECASE,
        ),
    ),
    (
        "projects",
        re.compile(
            r"((personal|selected|side|academic|notable) )?projects|portfolio",
            re.IGNORECASE,
        ),
    ),
    (
        "certifications",
        re.compile(
            r"certifications?|certificates|licenses?( (&|and) certifications?)?"
            r"|courses",
            re.IGNORECASE,
        ),
    ),
]

_MAX_HEADER_LENGTH = 60


@dataclass(frozen=True)
class ResumeSection:
    kind: str
    start: int  # offset of first content char after the header line
    end: int


@dataclass(frozen=True)
class ResumeLayout:
    sections: list[ResumeSection]
    header_end: int  # everything before the first section header: contact block

    def section(self, kind: str) -> ResumeSection | None:
        for s in self.sections:
            if s.kind == kind:
                return s
        return None


def detect_layout(text: str) -> ResumeLayout:
    headers: list[tuple[str, int, int]] = []  # (kind, header_start, header_end)
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip().strip(":•·-–—|").strip()
        if 0 < len(stripped) <= _MAX_HEADER_LENGTH:
            for kind, pattern in _HEADER_PATTERNS:
                if pattern.fullmatch(stripped):
                    headers.append((kind, offset, offset + len(line)))
                    break
        offset += len(line) + 1

    sections: list[ResumeSection] = []
    for i, (kind, _, header_end) in enumerate(headers):
        content_start = min(header_end + 1, len(text))
        content_end = headers[i + 1][1] if i + 1 < len(headers) else len(text)
        if content_start < content_end:
            sections.append(ResumeSection(kind=kind, start=content_start, end=content_end))

    header_block_end = headers[0][1] if headers else len(text)
    return ResumeLayout(sections=sections, header_end=header_block_end)

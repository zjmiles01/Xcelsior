"""Deterministic PDF → plain text for uploaded resumes.

pypdf only (pure Python, no system deps): same bytes in, same text out.
The normalized text returned here is what gets persisted as
`resumes.extracted_text`, and every downstream evidence offset indexes
into it — so normalization happens exactly once, here, and nothing after
this module may rewrite the text.

Failures are typed and loud: a scanned (image-only) PDF is rejected, not
silently OCR'd or stored empty; the review UI surfaces the rejection.
`RESUME_PARSER_VERSION` bumps whenever extraction or normalization
changes, so stored resumes can be re-parsed from their bytes (the
resume-side analog of `extractor_version` over raw postings).
"""

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

PARSER_NAME = "pypdf"
RESUME_PARSER_VERSION = 1

# Below this many non-whitespace characters the "resume" is either a blank
# or a scan with no text layer; storing it would make every later stage
# fail confusingly instead of failing loudly here.
_MIN_TEXT_CHARS = 40

_PDF_MAGIC = b"%PDF-"
_BLANK_RUNS = re.compile(r"\n{3,}")


class ResumeParseError(Exception):
    """The uploaded document could not be turned into resume text."""


class NotAPdfError(ResumeParseError):
    pass


class EncryptedPdfError(ResumeParseError):
    pass


class NoTextError(ResumeParseError):
    """Structurally valid PDF with no usable text layer (likely a scan)."""


@dataclass(frozen=True)
class ParsedResume:
    text: str
    page_count: int


def parse_pdf(data: bytes) -> ParsedResume:
    if not data.startswith(_PDF_MAGIC):
        raise NotAPdfError("file is not a PDF (missing %PDF header)")

    try:
        reader = PdfReader(BytesIO(data))
        # Some tools set an owner password with an empty user password;
        # those open fine. A real user password is a hard stop.
        if reader.is_encrypted and not reader.decrypt(""):
            raise EncryptedPdfError("PDF is password-protected")
        pages = [page.extract_text() or "" for page in reader.pages]
    except EncryptedPdfError:
        raise
    except PyPdfError as exc:
        raise NotAPdfError(f"PDF could not be read: {exc}") from exc

    text = _normalize("\n\n".join(pages))
    if len(re.sub(r"\s", "", text)) < _MIN_TEXT_CHARS:
        raise NoTextError("PDF has no extractable text layer (scanned image?)")
    return ParsedResume(text=text, page_count=len(pages))


def _normalize(raw: str) -> str:
    lines = [line.rstrip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip("\n")

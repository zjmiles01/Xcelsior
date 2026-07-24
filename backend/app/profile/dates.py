"""Date-range grammar for resume entries: "Mar 2022 - Present",
"July 2019 to Feb 2022", "03/2020 - 06/2023", "2015 - 2019".

Deliberately tight: month-name/month-number + year forms and bare years
only. A date we can't parse stays unparsed (the entry keeps its evidence
text and the user fills the date in during review) — never guessed.
"""

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_NAME = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?"
    r"|nov(?:ember)?|dec(?:ember)?"
)
_YEAR = r"(?:19|20)\d{2}"

def _token(n: int) -> str:
    """One date token: "Mar 2022", "March 2022", "03/2022", or "2022"."""
    return (
        rf"(?:(?P<mname{n}>{_MONTH_NAME})\.?,?\s+(?P<myear{n}>{_YEAR})"
        rf"|(?P<mnum{n}>0?[1-9]|1[0-2])/(?P<nyear{n}>{_YEAR})"
        rf"|(?P<bare{n}>{_YEAR}))"
    )


_SEPARATOR = r"\s*(?:-|–|—|to|through|until)\s*"
_OPEN_END = r"(?P<open>present|current|now|ongoing|today)"

_RANGE_RE = re.compile(
    rf"\b{_token(1)}{_SEPARATOR}(?:{_token(2)}|{_OPEN_END})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateRange:
    start: date  # month precision at best; day is always 1
    end: date | None  # None while is_current
    is_current: bool
    match_start: int  # span within the searched string
    match_end: int


def _token_date(m: re.Match, n: int) -> date:
    mname = m.group(f"mname{n}")
    if mname:
        # First three letters identify every month ("sept"[:3] == "sep").
        return date(int(m.group(f"myear{n}")), _MONTHS[mname.lower()[:3]], 1)
    mnum = m.group(f"mnum{n}")
    if mnum:
        return date(int(m.group(f"nyear{n}")), int(mnum), 1)
    return date(int(m.group(f"bare{n}")), 1, 1)


def find_date_range(text: str) -> DateRange | None:
    """First parseable range in `text`, or None. Start must not be after
    end (a reversed range is a parse we don't trust)."""
    m = _RANGE_RE.search(text)
    if not m:
        return None
    start = _token_date(m, 1)
    if m.group("open"):
        return DateRange(start, None, True, m.start(), m.end())
    end = _token_date(m, 2)
    if start > end:
        return None
    return DateRange(start, end, False, m.start(), m.end())
